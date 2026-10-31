/**
 * Who's signed in. One TanStack Query, `useSession()`, is the single source of
 * truth for both the user and the CSRF token. Sign-in, registration and
 * sign-out update it directly from their responses (no extra request).
 */
import { type QueryClient, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiSend, fetchSession, onSessionRefreshed, type Session, setCsrfToken } from "../../api/client";
import type { components } from "../../api/schema";

export type LoginIn = components["schemas"]["LoginIn"];
export type RegisterIn = components["schemas"]["RegisterIn"];
export type User = NonNullable<Session["user"]>;

export const sessionQueryKey = ["session"] as const;
/** Every query holding the signed-in user's own data starts with this. */
export const userDataKey = ["me"] as const;

/**
 * Store a new session. When the signed-in user changes (sign-in, sign-out,
 * expiry), drop the previous user's cached data so nobody sees someone else's.
 */
function storeSession(queryClient: QueryClient, session: Session): void {
  const previous = queryClient.getQueryData<Session>(sessionQueryKey);
  if (previous?.user?.email !== session.user?.email) {
    queryClient.removeQueries({ queryKey: userDataKey });
  }
  queryClient.setQueryData(sessionQueryKey, session);
}

/**
 * Keep the session query in sync when the API client refreshes the session on
 * its own (after a csrf_failed). Call once per QueryClient.
 */
export function connectSessionCache(queryClient: QueryClient): void {
  onSessionRefreshed((session) => {
    storeSession(queryClient, session);
  });
}

export function useSession() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ signal }) => fetchSession(signal),
    // The session only changes through the mutations below or a CSRF refresh,
    // all of which update this query directly, so never refetch on our own.
    staleTime: Infinity,
    retry: 1,
  });
}

function useSessionMutation<TInput>(request: (input: TInput) => Promise<Session>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (session) => {
      setCsrfToken(session.csrf_token); // rotated by the server on sign-in/out
      storeSession(queryClient, session);
    },
  });
}

export function useLogin() {
  return useSessionMutation((body: LoginIn) => apiSend<Session>("POST", "/api/auth/login", body));
}

export function useRegister() {
  return useSessionMutation((body: RegisterIn) =>
    apiSend<Session>("POST", "/api/auth/register", body),
  );
}

export function useLogout() {
  return useSessionMutation(() => apiSend<Session>("POST", "/api/auth/logout"));
}

/**
 * Delete the account (DELETE /api/me, password required). The server signs the
 * user out; `onDeleted` should go to a public page, which then calls
 * useRefreshSession(). Clearing the session here instead would let the sign-in
 * guard redirect first: React Router navigates in a low-priority transition.
 */
export function useDeleteAccount(onDeleted: () => void) {
  return useMutation({
    mutationFn: (password: string) => apiSend<Session>("DELETE", "/api/me", { password }),
    onSuccess: onDeleted,
  });
}

/** Forget the previous user's cached data and ask the server who's signed in now. */
export function useRefreshSession() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.removeQueries({ queryKey: userDataKey });
    return queryClient.invalidateQueries({ queryKey: sessionQueryKey });
  };
}
