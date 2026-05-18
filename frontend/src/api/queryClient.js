/**
 * Singleton QueryClient configuration.
 *
 * Cache defaults are tuned for an operator console:
 *   - 30s staleTime keeps detail screens snappy without burying the API
 *     in chatter on tab focus.
 *   - 4xx responses are NOT retried (they're not transient).
 *   - Network / 5xx responses retry up to twice with exponential backoff.
 *   - Mutations never auto-retry; the SPA decides per-action.
 */
import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "./client.js";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          if (error instanceof ApiError) {
            // Don't bother retrying client errors.
            if (error.status >= 400 && error.status < 500) return false;
          }
          return failureCount < 2;
        },
        retryDelay: (attempt) => Math.min(2000 * 2 ** attempt, 10_000),
      },
      mutations: {
        retry: false,
      },
    },
  });
}
