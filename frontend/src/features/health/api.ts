import { useQuery } from "@tanstack/react-query";

import { apiGet } from "../../api/client";

/** Mirrors `HealthOut` in backend/src/screening_room/health.py. */
export interface HealthResponse {
  status: "ok" | "unavailable";
  database: "ok" | "unavailable";
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: ({ signal }) => apiGet<HealthResponse>("/api/health", { signal }),
    // A health check should report the current state, not retry until it changes.
    retry: false,
  });
}
