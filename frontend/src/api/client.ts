/**
 * Thin fetch wrapper for the Screening Room API.
 *
 * Paths are same-origin (`/api/...`): in development Vite proxies them to
 * FastAPI, and the browser sends the session cookie automatically.
 *
 * CSRF (security.md §5): the token from GET /api/auth/session is kept in
 * memory and sent as X-CSRF-Token on every unsafe request. If the API answers
 * `csrf_failed` (the token went stale: session expired, secret rotated...),
 * the client fetches a fresh token and retries the request once. That's safe
 * because a request rejected by the CSRF check was never processed.
 *
 * Request and response types come from ./schema.ts, which is generated from the
 * backend's OpenAPI schema (`npm run api:types`). Never edit it by hand.
 */
import type { components } from "./schema";

export type ErrorResponse = components["schemas"]["ErrorResponse"];
export type FieldError = components["schemas"]["FieldError"];
export type Session = components["schemas"]["SessionOut"];

export const SESSION_PATH = "/api/auth/session";

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

// --- CSRF token and session refresh ------------------------------------------------

// In memory only, never localStorage (security.md §5.2).
let csrfToken: string | null = null;
let sessionRefreshedListener: ((session: Session) => void) | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

/** Called with the new session whenever the client had to refresh it. */
export function onSessionRefreshed(listener: ((session: Session) => void) | null): void {
  sessionRefreshedListener = listener;
}

/** GET /api/auth/session, remembering its CSRF token for later requests. */
export async function fetchSession(signal?: AbortSignal): Promise<Session> {
  const session = await send<Session>("GET", SESSION_PATH, undefined, signal);
  setCsrfToken(session.csrf_token);
  return session;
}

// --- Requests ------------------------------------------------------------------------

type UnsafeMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export function apiGet<T>(path: string, init?: { signal?: AbortSignal }): Promise<T> {
  return send<T>("GET", path, undefined, init?.signal);
}

/** A POST/PUT/PATCH/DELETE with a JSON body and the CSRF header. */
export async function apiSend<T>(method: UnsafeMethod, path: string, body?: unknown): Promise<T> {
  try {
    return await send<T>(method, path, body);
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== "csrf_failed") {
      throw error; // includes origin_rejected, which a retry can't fix
    }
    const session = await fetchSession();
    sessionRefreshedListener?.(session);
    // Retry exactly once. If the user turned out to be signed out, a protected
    // request now fails with 401, and the refreshed session sends the UI to
    // sign-in; a sign-in request simply succeeds with the fresh anonymous token.
    return send<T>(method, path, body);
  }
}

async function send<T>(
  method: "GET" | UnsafeMethod,
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json"; // the API accepts JSON only
  }
  if (method !== "GET" && csrfToken !== null) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? null : JSON.stringify(body),
    signal: signal ?? null,
  });
  const responseBody: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, responseBody);
  }
  // T comes from the generated types, which describe what the server sends.
  return responseBody as T;
}
