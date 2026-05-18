import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as findings from "../api/findings.js";

export function useFindings(params) {
  return useQuery({
    queryKey: ["findings", params],
    queryFn: () => findings.listFindings(params),
    placeholderData: (prev) => prev,
  });
}

export function useFinding(id) {
  return useQuery({
    queryKey: ["finding", id],
    queryFn: () => findings.getFinding(id),
    enabled: Boolean(id),
  });
}

export function useSuppressFinding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => findings.suppressFinding(id, body || {}),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["finding", id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
    },
  });
}

export function useMarkFindingFixed() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => findings.markFindingFixed(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["finding", id] });
      qc.invalidateQueries({ queryKey: ["findings"] });
    },
  });
}

export function useRunRepairForFinding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => findings.runRepairForFinding(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
