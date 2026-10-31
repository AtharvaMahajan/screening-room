/**
 * Discover: ask for an explained shortlist (POST /api/recommendations).
 *
 * POST, because every call is logged (recommendation-engine.md §15), so it's a
 * mutation, not a query: nothing refetches on its own. The latest shortlist is
 * kept in the query cache, so opening a title and coming back still shows it,
 * and signing out drops it with the rest of the user's data (auth/api.ts).
 */
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiSend } from "../../api/client";
import type { components } from "../../api/schema";
import { userDataKey } from "../auth/api";
import { type TitleState, useStoreTitleState } from "../library/api";

type RecommendationRequest = components["schemas"]["RecommendationRequestIn"];
export type Recommendations = components["schemas"]["RecommendationsOut"];
export type Recommendation = components["schemas"]["RecommendationOut"];
export type Reason = components["schemas"]["ReasonOut"];

/** What the user asked for this time. Every part is optional. */
export interface DiscoverContext {
  media_type: "movie" | "tv" | "any";
  genre_id: number | null;
  max_runtime_minutes: number | null; // movies only
}

export const ANY_CONTEXT: DiscoverContext = {
  media_type: "any",
  genre_id: null,
  max_runtime_minutes: null,
};

export interface DiscoverState {
  context: DiscoverContext;
  shortlist: Recommendations;
  /** Every title shown for this context so far: "show me more" leaves them out. */
  seenIds: number[];
  /** Hidden from this shortlist: skipped (ephemeral, ADR-0009) or marked not for me. */
  hiddenIds: number[];
}

export const SHORTLIST_SIZE = 5; // the most the API returns
const MAX_EXCLUDED = 100; // the API's limit: send the most recent ones
const discoverKey = [...userDataKey, "discover"] as const;

/** The current shortlist, if any. Only ever set by the hooks below. */
export function useDiscoverState() {
  return useQuery<DiscoverState>({
    queryKey: discoverKey,
    queryFn: skipToken, // never fetched: it's the result of the last request
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/**
 * Request a shortlist. `more: true` asks for titles not shown yet, for the
 * same context; otherwise it's a fresh start with this context.
 */
export function useRecommend() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ context, seenIds }: { context: DiscoverContext; seenIds: number[] }) =>
      apiSend<Recommendations>("POST", "/api/recommendations", toRequest(context, seenIds)),
    onSuccess: (shortlist, { context, seenIds }) => {
      const newIds = shortlist.results.map((result) => result.title.id);
      queryClient.setQueryData<DiscoverState>(discoverKey, {
        context,
        shortlist,
        seenIds: [...seenIds, ...newIds],
        hiddenIds: [],
      });
    },
  });
}

/** Take a card off the current shortlist (it stays excluded from "show me more"). */
export function useHide() {
  const queryClient = useQueryClient();
  return (titleId: number) => {
    queryClient.setQueryData<DiscoverState>(discoverKey, (state) =>
      state && { ...state, hiddenIds: [...state.hiddenIds, titleId] },
    );
  };
}

export type ResultEvent = components["schemas"]["ResultEventIn"];

/**
 * Record what the user did with a result: save, watch, rate, not for me, skip,
 * open. The server applies the library change with attribution (M4c) and
 * returns the title's new library state, which updates every view of it.
 */
export function useResultEvent(resultId: number) {
  const store = useStoreTitleState();
  return useMutation({
    mutationFn: (event: ResultEvent) =>
      apiSend<TitleState>("POST", `/api/recommendations/results/${String(resultId)}/events`, event),
    scope: { id: `result-${String(resultId)}` },
    onSuccess: store,
  });
}

function toRequest(context: DiscoverContext, seenIds: number[]): RecommendationRequest {
  return {
    media_type: context.media_type,
    genre_ids: context.genre_id === null ? [] : [context.genre_id],
    // A runtime limit only applies to movies (R4), so TV requests don't send one.
    max_runtime_minutes: context.media_type === "tv" ? null : context.max_runtime_minutes,
    exclude_title_ids: seenIds.slice(-MAX_EXCLUDED),
    limit: SHORTLIST_SIZE,
  };
}
