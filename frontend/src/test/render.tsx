import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

import { createQueryClient } from "../app/queryClient";
import { routes } from "../app/routes";

/**
 * Render the real route table at `path`, with a fresh QueryClient per test.
 * Returns the router too, so tests can check where navigation ended up.
 */
export function renderAt(path: string) {
  const queryClient = createQueryClient();
  // Fail fast in tests instead of retrying.
  queryClient.setDefaultOptions({
    queries: { ...queryClient.getDefaultOptions().queries, retry: false },
  });
  const router = createMemoryRouter(routes, { initialEntries: [path] });

  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, router };
}
