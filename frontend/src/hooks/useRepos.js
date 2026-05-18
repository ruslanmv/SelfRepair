import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as repos from "../api/repos.js";

export function useRepos(params) {
  return useQuery({
    queryKey: ["repos", params],
    queryFn: () => repos.listRepos(params),
    placeholderData: (prev) => prev,
  });
}

export function useRepo(id) {
  return useQuery({
    queryKey: ["repo", id],
    queryFn: () => repos.getRepo(id),
    enabled: Boolean(id),
  });
}

export function useRepoSummary(id) {
  return useQuery({
    queryKey: ["repo-summary", id],
    queryFn: () => repos.getRepoSummary(id),
    enabled: Boolean(id),
  });
}

export function useRepoConfig(id) {
  return useQuery({
    queryKey: ["repo-config", id],
    queryFn: () => repos.getRepoConfig(id),
    enabled: Boolean(id),
  });
}

export function useInvalidateRepo() {
  const qc = useQueryClient();
  return (id) => {
    qc.invalidateQueries({ queryKey: ["repo", id] });
    qc.invalidateQueries({ queryKey: ["repo-summary", id] });
    qc.invalidateQueries({ queryKey: ["repos"] });
  };
}

export function useSyncRepos() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => repos.syncRepos(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

export { useMutation };
