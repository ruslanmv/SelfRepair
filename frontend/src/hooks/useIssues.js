import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as issues from "../api/issues.js";

export function useIssues(params) {
  return useQuery({
    queryKey: ["issues", params],
    queryFn: () => issues.listIssues(params),
    placeholderData: (prev) => prev,
  });
}

export function useIssue(id) {
  return useQuery({
    queryKey: ["issue", id],
    queryFn: () => issues.getIssue(id),
    enabled: Boolean(id),
  });
}

export function useSyncIssues() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => issues.syncIssues(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues"] }),
  });
}

export function useRunRepairFromIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => issues.runRepairFromIssue(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["issue", id] });
      qc.invalidateQueries({ queryKey: ["issues"] });
    },
  });
}

export function useTriageIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => issues.triageIssue(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues"] }),
  });
}

export function useCommentOnIssue() {
  return useMutation({
    mutationFn: ({ id, body }) => issues.commentOnIssue(id, body),
  });
}

export function useSuppressIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => issues.suppressIssue(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues"] }),
  });
}
