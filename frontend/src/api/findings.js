import { api, qs } from "./client.js";

export const listFindings = (params) => api(`/v1/findings${qs(params)}`);
export const getFinding = (id) => api(`/v1/findings/${id}`);
export const suppressFinding = (id, body) =>
  api(`/v1/findings/${id}/suppress`, { method: "POST", body });
export const markFindingFixed = (id) =>
  api(`/v1/findings/${id}/mark-fixed`, { method: "POST" });
export const runRepairForFinding = (id) =>
  api(`/v1/findings/${id}/run-repair`, { method: "POST" });
