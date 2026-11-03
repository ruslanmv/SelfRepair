import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as reviews from "../api/reviews.js";

export function useReviews(params) {
  return useQuery({
    queryKey: ["reviews", params],
    queryFn: () => reviews.listReviews(params),
  });
}

export function useReview(id) {
  return useQuery({
    queryKey: ["review", id],
    queryFn: () => reviews.getReview(id),
    enabled: Boolean(id),
    retry: (count, error) => error?.status !== 404 && count < 2,
  });
}

export function useReviewFindings(id) {
  return useQuery({
    queryKey: ["review-findings", id],
    queryFn: () => reviews.listReviewFindings(id),
    enabled: Boolean(id),
    retry: (count, error) => error?.status !== 404 && count < 2,
  });
}

export function useRemediations(id) {
  return useQuery({
    queryKey: ["review-remediations", id],
    queryFn: () => reviews.listRemediations(id),
    enabled: Boolean(id),
    retry: (count, error) => error?.status !== 404 && count < 2,
  });
}

export function useRetryReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reviews.retryReview,
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["review", id] });
      qc.invalidateQueries({ queryKey: ["reviews"] });
    },
  });
}

export function useRequestRemediation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => reviews.requestRemediation(id, body),
    onSuccess: (_data, { id }) =>
      qc.invalidateQueries({ queryKey: ["review-remediations", id] }),
  });
}

export function useOrgReviewSettings() {
  return useQuery({
    queryKey: ["review-settings"],
    queryFn: reviews.getOrgReviewSettings,
  });
}

export function usePutOrgReviewSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: reviews.putOrgReviewSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["review-settings"] }),
  });
}
