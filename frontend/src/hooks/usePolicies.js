import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as policies from "../api/policies.js";

export function usePolicies(params) {
  return useQuery({
    queryKey: ["policies", params],
    queryFn: () => policies.listPolicies(params),
  });
}

export function usePolicy(id) {
  return useQuery({
    queryKey: ["policy", id],
    queryFn: () => policies.getPolicy(id),
    enabled: Boolean(id),
  });
}

export function usePolicyDecisions(params) {
  return useQuery({
    queryKey: ["policy-decisions", params],
    queryFn: () => policies.listPolicyDecisions(params),
  });
}

export function useUploadPolicyBundle() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => policies.uploadBundle(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });
}

export function useEvaluatePolicy() {
  return useMutation({
    mutationFn: (body) => policies.evaluatePolicy(body),
  });
}
