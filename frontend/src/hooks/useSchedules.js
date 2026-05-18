import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as schedules from "../api/schedules.js";

export function useSchedules() {
  return useQuery({
    queryKey: ["schedules"],
    queryFn: () => schedules.listSchedules(),
  });
}

export function useSchedule(id) {
  return useQuery({
    queryKey: ["schedule", id],
    queryFn: () => schedules.getSchedule(id),
    enabled: Boolean(id),
  });
}

export function useCreateSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body) => schedules.createSchedule(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}

export function usePatchSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => schedules.patchSchedule(id, body),
    onSuccess: (_data, { id }) => {
      qc.invalidateQueries({ queryKey: ["schedule", id] });
      qc.invalidateQueries({ queryKey: ["schedules"] });
    },
  });
}

export function useDeleteSchedule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => schedules.deleteSchedule(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["schedules"] }),
  });
}
