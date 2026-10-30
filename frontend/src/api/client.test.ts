import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  apiGet,
  apiSend,
  fetchSession,
  onSessionRefreshed,
  type Session,
  SESSION_PATH,
  setCsrfToken,
} from "./client";

function stubFetch(response: Response) {
  const fetchMock = vi.fn(() => Promise.resolve(response));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function apiGetError(path: string): Promise<unknown> {
  return apiGet(path).catch((e: unknown) => e);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet", () => {
  it("returns the parsed JSON body on success", async () => {
    const fetchMock = stubFetch(Response.json({ status: "ok" }));

    await expect(apiGet("/api/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("exposes code and message from the standard error body", async () => {
    stubFetch(
      Response.json(
        { error: { code: "database_unavailable", message: "The database is unavailable." } },
        { status: 503 },
      ),
    );

    const error = await apiGetError("/api/health");

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 503,
      code: "database_unavailable",
      message: "The database is unavailable.",
      details: [],
    });
  });

  it("exposes field details from a validation error", async () => {
    const details = [{ field: "body.email", message: "Field required" }];
    stubFetch(
      Response.json(
        { error: { code: "validation_failed", message: "The request is invalid.", details } },
        { status: 422 },
      ),
    );

    await expect(apiGetError("/api/anything")).resolves.toMatchObject({ details });
  });

  it.each([
    ["a non-JSON body", new Response("Bad Gateway", { status: 502 })],
    ["JSON in another shape", Response.json({ detail: "Not Found" }, { status: 404 })],
  ])("falls back to unknown_error for %s", async (_, response) => {
    stubFetch(response);

    const error = await apiGetError("/api/health");

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: response.status, code: "unknown_error" });
  });
});

// --- CSRF (security.md §5) --------------------------------------------------------------

const csrfFailed = () =>
  Response.json({ error: { code: "csrf_failed", message: "CSRF check failed." } }, { status: 403 });

function session(user: Session["user"], csrfToken: string): Response {
  return Response.json({ user, csrf_token: csrfToken } satisfies Session);
}

/** Each call to fetch returns the next response; returns the mock for inspection. */
function stubFetchSequence(...responses: Response[]) {
  const fetchMock = vi.fn<typeof fetch>();
  for (const response of responses) {
    fetchMock.mockResolvedValueOnce(response);
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestOf(fetchMock: ReturnType<typeof stubFetchSequence>, call: number) {
  const [path, init] = fetchMock.mock.calls[call] ?? [];
  return { path, method: init?.method, headers: init?.headers as Record<string, string> };
}

describe("apiSend", () => {
  beforeEach(() => {
    setCsrfToken("token-1");
    onSessionRefreshed(null);
  });

  it("sends JSON with the CSRF token", async () => {
    const fetchMock = stubFetchSequence(Response.json({ ok: true }));

    await apiSend("POST", "/api/things", { name: "x" });

    const request = requestOf(fetchMock, 0);
    expect(request.method).toBe("POST");
    expect(request.headers).toMatchObject({
      "Content-Type": "application/json",
      "X-CSRF-Token": "token-1",
    });
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe('{"name":"x"}');
  });

  it("does not send the CSRF token on GET requests", async () => {
    const fetchMock = stubFetchSequence(Response.json({}));

    await apiGet("/api/health");

    expect(requestOf(fetchMock, 0).headers).not.toHaveProperty("X-CSRF-Token");
  });

  it("on csrf_failed, refreshes the token and retries once", async () => {
    const user = { email: "ada@example.com", display_name: null };
    const listener = vi.fn();
    onSessionRefreshed(listener);
    const fetchMock = stubFetchSequence(
      csrfFailed(),
      session(user, "token-2"),
      Response.json({ ok: true }),
    );

    await expect(apiSend("POST", "/api/things", {})).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(requestOf(fetchMock, 1).path).toBe(SESSION_PATH);
    expect(requestOf(fetchMock, 2).headers["X-CSRF-Token"]).toBe("token-2");
    expect(listener).toHaveBeenCalledWith({ user, csrf_token: "token-2" });
  });

  it("retries a sign-in with a fresh anonymous token", async () => {
    // e.g. the anonymous token went stale while the sign-in page sat open
    const fetchMock = stubFetchSequence(
      csrfFailed(),
      session(null, "anon-2"),
      session({ email: "ada@example.com", display_name: null }, "signed-in"),
    );

    await apiSend("POST", "/api/auth/login", { email: "ada@example.com", password: "x" });

    expect(requestOf(fetchMock, 2).headers["X-CSRF-Token"]).toBe("anon-2");
  });

  it("gives up after one retry", async () => {
    const fetchMock = stubFetchSequence(csrfFailed(), session(null, "anon-2"), csrfFailed());

    const error = await apiSend("POST", "/api/things").catch((e: unknown) => e);

    expect(error).toMatchObject({ code: "csrf_failed" });
    expect(fetchMock).toHaveBeenCalledTimes(3); // no loop
  });

  it("never retries origin_rejected", async () => {
    const fetchMock = stubFetchSequence(
      Response.json({ error: { code: "origin_rejected", message: "No." } }, { status: 403 }),
    );

    await expect(apiSend("POST", "/api/things")).rejects.toMatchObject({
      code: "origin_rejected",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("fetchSession", () => {
  it("remembers the CSRF token for later unsafe requests", async () => {
    const fetchMock = stubFetchSequence(session(null, "from-session"), Response.json({}));

    await fetchSession();
    await apiSend("POST", "/api/things");

    expect(requestOf(fetchMock, 1).headers["X-CSRF-Token"]).toBe("from-session");
  });
});
