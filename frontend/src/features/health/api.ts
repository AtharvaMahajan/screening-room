import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../../api/client";
import type { components } from "../../api/schema";

export type HealthResponse = components["schemas"]["HealthOut"];

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => apiGet<HealthResponse>("/api/health", { signal }),
    // A health check should report the current state, not retry until it changes.
    retry: false,
  });
}
