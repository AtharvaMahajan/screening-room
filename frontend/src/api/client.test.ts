import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "./client";

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(() => Promise.resolve(Response.json(body, { status })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiGet", () => {
  it("returns the parsed JSON body on success", async () => {
    const fetchMock = stubFetch(200, { status: "ok" });

    await expect(apiGet("/api/health")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.anything());
  });

  it("throws ApiError with status and body on a non-2xx response", async () => {
    stubFetch(503, { status: "unavailable" });

    const error: unknown = await apiGet("/api/health").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, body: { status: "unavailable" } });
  });
});
