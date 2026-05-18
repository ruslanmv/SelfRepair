import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as jobs from "../api/jobs.js";

export function useJobs(params) {
  return useQuery({
    queryKey: ["jobs", params],
    queryFn: () => jobs.listJobs(params),
    placeholderData: (prev) => prev,
  });
}

export function useJob(id) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => jobs.getJob(id),
    enabled: Boolean(id),
    refetchInterval: (q) => {
      // Active jobs poll every 5s as a fallback in case SSE is unavailable.
      const data = q.state.data;
      const state = data?.state;
      const live = new Set([
        "queued",
        "cloning",
        "analyzing",
        "scanning",
        "planning",
        "repairing",
        "validating",
        "publishing",
      ]);
      return state && live.has(state) ? 5000 : false;
    },
  });
}

export function useJobEvents(id, params) {
  return useQuery({
    queryKey: ["job-events", id, params],
    queryFn: () => jobs.listJobEvents(id, params),
    enabled: Boolean(id),
  });
}

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => jobs.createJob(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => jobs.cancelJob(id),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["job", id] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useRetryJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => jobs.retryJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}
