/**
 * A fake of the library API for component tests: remembers each title's state
 * and applies the same rules as the backend (data-model.md §5), e.g. watching
 * takes a title off the watchlist and rating marks it watched.
 * Spread its handlers into mockApi().
 */
import type { components } from "../api/schema";

type TitleState = components["schemas"]["TitleStateOut"];
type Handler = (body: unknown) => Response;

const empty = (titleId: number): TitleState => ({
  title_id: titleId,
  in_watchlist: false,
  watch_count: 0,
  last_watched_on: null,
  rating: null,
  not_for_me: false,
});

export function fakeLibrary(titleIds: number[], resultTitles: Record<number, number> = {}) {
  const states = new Map(titleIds.map((id) => [id, empty(id)]));
  const get = (id: number) => states.get(id) ?? empty(id);
  const update = (id: number, change: Partial<TitleState>): Response => {
    const next = { ...get(id), ...change };
    states.set(id, next);
    return Response.json(next);
  };
  const watch = (id: number, on: string | null): Partial<TitleState> => ({
    watch_count: get(id).watch_count + 1,
    in_watchlist: false,
    last_watched_on: on ?? get(id).last_watched_on,
  });

  const handlers: Record<string, Handler> = {};
  for (const id of titleIds) {
    const t = String(id);
    handlers[`GET /api/me/titles/${t}`] = () => Response.json(get(id));
    handlers[`PUT /api/me/watchlist/${t}`] = () => update(id, { in_watchlist: true });
    handlers[`DELETE /api/me/watchlist/${t}`] = () => update(id, { in_watchlist: false });
    handlers[`POST /api/me/history/${t}`] = (body) =>
      update(id, watch(id, (body as { watched_on: string | null }).watched_on));
    handlers[`DELETE /api/me/history/${t}`] = () =>
      update(id, { watch_count: 0, last_watched_on: null });
    handlers[`PUT /api/me/ratings/${t}`] = (body) =>
      update(id, {
        rating: (body as { value: number }).value,
        ...(get(id).watch_count === 0 ? watch(id, null) : {}),
      });
    handlers[`DELETE /api/me/ratings/${t}`] = () => update(id, { rating: null });
    handlers[`PUT /api/me/not-for-me/${t}`] = () => update(id, { not_for_me: true });
    handlers[`DELETE /api/me/not-for-me/${t}`] = () => update(id, { not_for_me: false });
  }
  for (const [resultId, titleId] of Object.entries(resultTitles)) {
    handlers[`POST /api/recommendations/results/${resultId}/events`] = (body) => {
      const event = body as { type: string; rating?: number };
      switch (event.type) {
        case "saved":
          return update(titleId, { in_watchlist: true });
        case "watched":
          return update(titleId, watch(titleId, null));
        case "rated":
          return update(titleId, {
            rating: event.rating ?? null,
            ...(get(titleId).watch_count === 0 ? watch(titleId, null) : {}),
          });
        case "not_for_me":
          return update(titleId, { not_for_me: true });
        default:
          return Response.json(get(titleId), { status: 201 });
      }
    };
  }
  return handlers;
}
