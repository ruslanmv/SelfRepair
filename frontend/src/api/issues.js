import { api, qs } from "./client.js";

export const listIssues = (params) => api(`/v1/issues${qs(params)}`);
export const getIssue = (id) => api(`/v1/issues/${id}`);
export const syncIssues = (body) =>
  api("/v1/issues/sync", { method: "POST", body });
export const runRepairFromIssue = (id, body) =>
  api(`/v1/issues/${id}/run-repair`, { method: "POST", body });
export const triageIssue = (id, body) =>
  api(`/v1/issues/${id}/triage`, { method: "POST", body });
export const commentOnIssue = (id, body) =>
  api(`/v1/issues/${id}/comment`, { method: "POST", body });
export const suppressIssue = (id, body) =>
  api(`/v1/issues/${id}/suppress`, { method: "POST", body });
