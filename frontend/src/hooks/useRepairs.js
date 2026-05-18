import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as repairs from "../api/repairs.js";

export function useRepairs(params) {
  return useQuery({
    queryKey: ["repairs", params],
    queryFn: () => repairs.listRepairs(params),
    placeholderData: (prev) => prev,
  });
}

export function useRepair(id) {
  return useQuery({
    queryKey: ["repair", id],
    queryFn: () => repairs.getRepair(id),
    enabled: Boolean(id),
  });
}

export function useRepairDiff(id) {
  return useQuery({
    queryKey: ["repair-diff", id],
    queryFn: () => repairs.getRepairDiff(id),
    enabled: Boolean(id),
  });
}

export function useRepairPolicy(id) {
  return useQuery({
    queryKey: ["repair-policy", id],
    queryFn: () => repairs.getRepairPolicy(id),
    enabled: Boolean(id),
  });
}

export function useRepairProvenance(id) {
  return useQuery({
    queryKey: ["repair-provenance", id],
    queryFn: () => repairs.getRepairProvenance(id),
    enabled: Boolean(id),
  });
}

function invalidateRepair(qc, id) {
  qc.invalidateQueries({ queryKey: ["repair", id] });
  qc.invalidateQueries({ queryKey: ["repair-policy", id] });
  qc.invalidateQueries({ queryKey: ["repairs"] });
}

export function useApproveRepair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => repairs.approveRepair(id, body || {}),
    onSuccess: (_data, { id }) => invalidateRepair(qc, id),
  });
}

export function useRejectRepair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => repairs.rejectRepair(id, body || {}),
    onSuccess: (_data, { id }) => invalidateRepair(qc, id),
  });
}

export function useRerunValidation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => repairs.rerunValidation(id),
    onSuccess: (_data, id) => invalidateRepair(qc, id),
  });
}

export function usePublishPr() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => repairs.publishPr(id),
    onSuccess: (_data, id) => invalidateRepair(qc, id),
  });
}
