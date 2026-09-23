import { api, qs } from "./client.js";

export const listRoutines = (params) => api(`/v1/routines${qs(params)}`);
export const getRoutine = (id) => api(`/v1/routines/${id}`);
export const createRoutine = (body) =>
  api("/v1/routines", { method: "POST", body });
export const patchRoutine = (id, body) =>
  api(`/v1/routines/${id}`, { method: "PATCH", body });
export const deleteRoutine = (id) =>
  api(`/v1/routines/${id}`, { method: "DELETE" });
export const setMergeLock = (id, body) =>
  api(`/v1/routines/${id}/merge-lock`, { method: "POST", body });
export const evaluateMergeGuard = (id, body) =>
  api(`/v1/routines/${id}/merge-guard`, { method: "POST", body });
export const listRoutineRuns = (id, params) =>
  api(`/v1/routines/${id}/runs${qs(params)}`);
export const getRoutineCapabilities = () => api("/v1/routines/capabilities");
