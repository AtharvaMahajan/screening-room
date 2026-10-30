/**
 * Thin fetch wrapper for the Screening Room API.
 *
 * Paths are same-origin (`/api/...`): in development Vite proxies them to
 * FastAPI. Later milestones add the CSRF header here (project-structure.md §8).
 *
 * Request and response types come from ./schema.ts, which is generated from the
 * backend's OpenAPI schema (`npm run api:types`). Never edit it by hand.
 */
import type { components } from "./schema";

export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type FieldError = components["schemas"]["FieldError"];

/**
 * A non-2xx response. `code` comes from the API's standard error body
 * ({"error": {"code", "message", "details"}}), so callers can branch on it.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: FieldError[];

  constructor(status: number, body: unknown) {
    const error = isErrorResponse(body) ? body.error : undefined;
    super(error?.message ?? `API request failed with status ${String(status)}`);
    this.name = "ApiError";
    this.status = status;
    // Responses that didn't come from our API (e.g. the dev proxy failing)
    // have no standard body.
    this.code = error?.code ?? "unknown_error";
    this.details = error?.details ?? [];
  }
}

function isErrorResponse(body: unknown): body is ErrorResponse {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return false;
  }
  const { error } = body;
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string"
  );
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
  // T comes from the generated types, which describe what the server sends.
  return body as T;
}
