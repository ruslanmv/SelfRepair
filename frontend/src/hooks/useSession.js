import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { ApiError } from "../api/client.js";
import * as auth from "../api/auth.js";

export function useSession() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => auth.me(),
    retry: false,
    staleTime: 60_000,
    // 401 means "not logged in" — return null instead of bubbling.
    throwOnError: (err) => !(err instanceof ApiError && err.status === 401),
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
