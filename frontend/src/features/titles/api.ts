import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiError, apiGet } from "../../api/client";
import type { components } from "../../api/schema";

export type TitleDetail = components["schemas"]["TitleDetailOut"];

export function useTitle(titleId: number) {
  return useQuery({
    queryKey: ["title", titleId],
    queryFn: ({ signal }) => apiGet<TitleDetail>(`/api/titles/${String(titleId)}`, { signal }),
    // A missing title or a bad request won't fix itself: only retry server trouble.
    retry: (failureCount, error) =>
      failureCount < 1 && !(error instanceof ApiError && error.status < 500),
  });
}

export type Genre = components["schemas"]["GenreOut"];
export type TitleCard = components["schemas"]["TitleCardOut"];

/** The genres people can like, avoid or filter by. They change only with a deploy. */
export function useGenres() {
  return useQuery({
    queryKey: ["genres"],
    queryFn: ({ signal }) => apiGet<Genre[]>("/api/genres", { signal }),
    staleTime: Infinity,
  });
}

/**
 * Local pool search (never TMDB). With an empty `query`: well-known titles in
 * `genreIds`, the "popular in your genres" suggestions.
 */
export function useTitleSearch(query: string, genreIds: readonly number[], limit: number) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (query) {
    params.set("q", query);
  } else {
    genreIds.forEach((id) => {
      params.append("genre_ids", String(id));
    });
  }
  return useQuery({
    queryKey: ["titles", "search", params.toString()],
    queryFn: ({ signal }) => apiGet<TitleCard[]>(`/api/titles?${params.toString()}`, { signal }),
    // Keep showing the last results while the next ones load: no flicker per keystroke.
    placeholderData: keepPreviousData,
  });
}

export type SearchResults = components["schemas"]["SearchOut"];

/**
 * Search TMDB for any movie or TV show (GET /api/search). `source: "local"` means
 * TMDB couldn't be reached, so only titles already in our catalog were searched.
 */
export function useCatalogSearch(query: string) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: ({ signal }) =>
      apiGet<SearchResults>(`/api/search?${new URLSearchParams({ q: query }).toString()}`, {
        signal,
      }),
    enabled: query.length > 0,
    staleTime: 5 * 60 * 1000, // the same words again shouldn't call TMDB again
    placeholderData: keepPreviousData,
  });
}
