import { useQuery } from "@tanstack/react-query";

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
