import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as routines from "../api/routines.js";

export function useRoutines(params) {
  return useQuery({
    queryKey: ["routines", params],
    queryFn: () => routines.listRoutines(params),
  });
}

export function useRoutineCapabilities() {
  return useQuery({
    queryKey: ["routine-capabilities"],
    queryFn: routines.getRoutineCapabilities,
  });
}

export function useCreateRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: routines.createRoutine,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routines"] }),
  });
}

export function usePatchRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => routines.patchRoutine(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routines"] }),
  });
}

export function useDeleteRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: routines.deleteRoutine,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routines"] }),
  });
}

export function useSetRoutineMergeLock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }) => routines.setMergeLock(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routines"] }),
  });
}

export function useRoutineRuns(id, params) {
  return useQuery({
    queryKey: ["routine-runs", id, params],
    queryFn: () => routines.listRoutineRuns(id, params),
    enabled: Boolean(id),
  });
}
