import { QueryClient } from "@tanstack/react-query";

import { connectSessionCache } from "../features/auth/api";

export function createQueryClient(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        // Avoid refetching on every tab switch; individual queries can opt in.
        refetchOnWindowFocus: false,
      },
    },
  });
  // When the API client refreshes the session itself (after a csrf_failed),
  // update the cached session too, so the UI reflects it immediately.
  connectSessionCache(queryClient);
  return queryClient;
}
