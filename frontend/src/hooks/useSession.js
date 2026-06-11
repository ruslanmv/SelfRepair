import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as auth from "../api/auth.js";

export function useSession() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => auth.me(),
    // Cold-start resilience: a 401 is a definitive "not logged in" (don't
    // retry → show Login fast). Any transient failure (network/status 0 or a
    // 5xx/504 while the HF Space is waking up) is retried with backoff so the
    // operator sees the loading spinner, then the app — not an error screen.
    retry: (failureCount, error) => {
      if (error && error.status === 401) return false;
      return failureCount < 6;
    },
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
    staleTime: 60_000,
    // Never bubble session errors to the error boundary. The App decides what
    // to render from `session.error.status` once retries are exhausted.
    throwOnError: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => auth.login(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => auth.logout(),
    onSuccess: () => {
      qc.removeQueries();
    },
  });
}

export function useRefreshSession() {
  return useMutation({
    mutationFn: () => auth.refresh(),
  });
}
