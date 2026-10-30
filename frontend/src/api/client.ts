/**
 * Thin fetch wrapper for the Screening Room API.
 *
 * Paths are same-origin (`/api/...`): in development Vite proxies them to
 * FastAPI. Later milestones add the CSRF header here (project-structure.md §8).
 */

/** A non-2xx response. `body` is the parsed JSON body, if there was one. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`API request failed with status ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export async function apiGet<T>(path: string, init?: { signal?: AbortSignal }): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    signal: init?.signal ?? null,
  });
  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  // Trusts the server's response shape. Generated OpenAPI types replace the
  // hand-written ones in a later milestone.
  return body as T;
}
