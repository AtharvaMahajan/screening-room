/**
 * The signed-in user's taste profile: genre preferences and favorite titles
 * (/api/me/..., data-model.md §3.3).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiGet, apiSend } from "../../api/client";
import type { components } from "../../api/schema";

export type Preferences = components["schemas"]["PreferencesOut"];
export type Favorites = components["schemas"]["FavoritesOut"];

const preferencesKey = ["me", "preferences"] as const;
const favoritesKey = ["me", "favorites"] as const;
const savePreferencesKey = ["me", "preferences", "save"] as const;

export function usePreferences() {
  return useQuery({
    queryKey: preferencesKey,
    queryFn: ({ signal }) => apiGet<Preferences>("/api/me/preferences", { signal }),
  });
}

/**
 * Save genre preferences on every change, updating the screen immediately.
 *
 * Each save sends the WHOLE new state (PUT replaces it), and saves run one at a
 * time in click order (`scope`), so the last click always wins on the server.
 * After the last save settles, the real state is refetched: that also undoes the
 * optimistic change if a save failed.
 */
export function useSavePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: savePreferencesKey,
    scope: { id: "save-preferences" },
    mutationFn: (preferences: Preferences) =>
      apiSend<Preferences>("PUT", "/api/me/preferences", preferences),
    onMutate: async (preferences) => {
      await queryClient.cancelQueries({ queryKey: preferencesKey });
      queryClient.setQueryData(preferencesKey, preferences);
    },
    onSettled: () => {
      // 1 = this save: only the last pending save refetches.
      if (queryClient.isMutating({ mutationKey: savePreferencesKey }) === 1) {
        void queryClient.invalidateQueries({ queryKey: preferencesKey });
      }
    },
  });
}

export function useFavorites() {
  return useQuery({
    queryKey: favoritesKey,
    queryFn: ({ signal }) => apiGet<Favorites>("/api/me/favorites", { signal }),
  });
}

/** Both endpoints return the full, updated list: use it as the new cache value. */
function useFavoritesMutation<TInput>(request: (input: TInput) => Promise<Favorites>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (favorites) => {
      queryClient.setQueryData(favoritesKey, favorites);
    },
  });
}

export function useAddFavorite() {
  return useFavoritesMutation((titleId: number) =>
    apiSend<Favorites>("POST", "/api/me/favorites", { title_id: titleId }),
  );
}

export function useRemoveFavorite() {
  return useFavoritesMutation((titleId: number) =>
    apiSend<Favorites>("DELETE", `/api/me/favorites/${String(titleId)}`),
  );
}
