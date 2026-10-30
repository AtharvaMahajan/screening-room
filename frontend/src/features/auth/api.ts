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

/**
 * Keep the session query in sync when the API client refreshes the session on
 * its own (after a csrf_failed). Call once per QueryClient.
 */
export function connectSessionCache(queryClient: QueryClient): void {
  onSessionRefreshed((session) => {
    queryClient.setQueryData(sessionQueryKey, session);
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
      queryClient.setQueryData(sessionQueryKey, session);
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
