import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "./client";

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
