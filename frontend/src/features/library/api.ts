/**
 * The signed-in user's library state for a title: watchlist, viewings, rating,
 * "not for me" (/api/me/..., data-model.md §5).
 *
 * One query per title, shared by every place that shows it (title page,
 * Discover cards). Every change returns the new state, which replaces the
 * cached one, so all of them agree without refetching.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiSend } from "../../api/client";
import type { components } from "../../api/schema";
import { userDataKey } from "../auth/api";

export type TitleState = components["schemas"]["TitleStateOut"];

export const titleStateKey = (titleId: number) => [...userDataKey, "titles", titleId] as const;

export function useTitleState(titleId: number) {
  return useQuery({
    queryKey: titleStateKey(titleId),
    queryFn: ({ signal }) => apiGet<TitleState>(`/api/me/titles/${String(titleId)}`, { signal }),
  });
}

/** Store a title's new state, as returned by any library change. */
export function useStoreTitleState() {
  const queryClient = useQueryClient();
  return (state: TitleState) => {
    queryClient.setQueryData(titleStateKey(state.title_id), state);
  };
}

export type LibraryChange =
  | { kind: "save" }
  | { kind: "unsave" }
  | { kind: "watched"; watchedOn: string | null }
  | { kind: "unwatch" }
  | { kind: "rate"; stars: number }
  | { kind: "unrate" }
  | { kind: "not_for_me" }
  | { kind: "undo_not_for_me" };

function send(titleId: number, change: LibraryChange): Promise<TitleState> {
  const id = String(titleId);
  switch (change.kind) {
    case "save":
      return apiSend("PUT", `/api/me/watchlist/${id}`);
    case "unsave":
      return apiSend("DELETE", `/api/me/watchlist/${id}`);
    case "watched":
      return apiSend("POST", `/api/me/history/${id}`, { watched_on: change.watchedOn });
    case "unwatch":
      return apiSend("DELETE", `/api/me/history/${id}`);
    case "rate":
      return apiSend("PUT", `/api/me/ratings/${id}`, { value: change.stars });
    case "unrate":
      return apiSend("DELETE", `/api/me/ratings/${id}`);
    case "not_for_me":
      return apiSend("PUT", `/api/me/not-for-me/${id}`);
    case "undo_not_for_me":
      return apiSend("DELETE", `/api/me/not-for-me/${id}`);
  }
}

/** Change a title's library state. Changes to one title run in click order. */
export function useLibraryChange(titleId: number) {
  const store = useStoreTitleState();
  return useMutation({
    mutationFn: (change: LibraryChange) => send(titleId, change),
    scope: { id: `library-${String(titleId)}` },
    onSuccess: store,
  });
}
