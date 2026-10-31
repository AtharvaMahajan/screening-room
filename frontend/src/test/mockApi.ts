/**
 * A fake API for component tests: maps "METHOD /path" to a response.
 * Unknown requests get a 404 in the API's error format, so a missing mock
 * shows up as a visible error rather than a hang.
 */
import { vi } from "vitest";

import type { Session } from "../api/client";

type Handler = (body: unknown) => Response | Promise<Response>;

export const ADA = { email: "ada@example.com", display_name: "Ada" };

export const signedOut = (): Response =>
  Response.json({ user: null, csrf_token: "anon-token" } satisfies Session);

export const signedIn = (user = ADA): Response =>
  Response.json({ user, csrf_token: "signed-in-token" } satisfies Session);

export const apiError = (status: number, code: string, message: string, details?: unknown[]) =>
  Response.json({ error: { code, message, ...(details ? { details } : {}) } }, { status });

/** fetch() accepts a string, a URL or a Request; this gets the URL from any of them. */
function urlOf(input: string | URL | Request): string {
  if (typeof input === "string") {
    return input;
  }
  return input instanceof URL ? input.href : input.url;
}

export function mockApi(routes: Record<string, Handler>) {
  const handlers: Record<string, Handler> = {
    "GET /api/health": () => Response.json({ status: "ok", database: "ok" }),
    ...routes,
  };
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const key = `${init?.method ?? "GET"} ${urlOf(input)}`;
    const handler = handlers[key];
    if (!handler) {
      return apiError(404, "not_found", `No mock for ${key}`);
    }
    const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    return handler(body);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The requests made to `METHOD /path`, as [body, headers] pairs. */
export function callsTo(fetchMock: ReturnType<typeof mockApi>, key: string) {
  return fetchMock.mock.calls
    .filter(([input, init]) => `${init?.method ?? "GET"} ${urlOf(input)}` === key)
    .map(([, init]) => ({
      body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined,
      headers: init?.headers as Record<string, string>,
    }));
}

/** A new user's taste profile and a two-genre catalog, for pages that load them. */
export const emptyTasteProfile: Record<string, Handler> = {
  "GET /api/genres": () =>
    Response.json([
      { id: 7, slug: "drama", name: "Drama" },
      { id: 16, slug: "science-fiction", name: "Science Fiction" },
    ]),
  "GET /api/me/preferences": () => Response.json({ liked_genre_ids: [], avoided_genre_ids: [] }),
  "GET /api/me/favorites": () => Response.json({ favorites: [], max_favorites: 10 }),
  "GET /api/titles?limit=12": () => Response.json([]),
};
