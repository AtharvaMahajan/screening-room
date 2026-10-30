import { QueryClient } from "@tanstack/react-query";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Avoid refetching on every tab switch; individual queries can opt in.
        refetchOnWindowFocus: false,
      },
    },
  });
}
