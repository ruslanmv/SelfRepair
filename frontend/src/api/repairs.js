import { api, qs } from "./client.js";

export const listRepairs = (params) => api(`/v1/repairs${qs(params)}`);
export const getRepair = (id) => api(`/v1/repairs/${id}`);
export const getRepairDiff = (id) => api(`/v1/repairs/${id}/diff`);
export const getRepairPolicy = (id) => api(`/v1/repairs/${id}/policy`);
export const getRepairProvenance = (id) =>
  api(`/v1/repairs/${id}/provenance`);

export const approveRepair = (id, body) =>
  api(`/v1/repairs/${id}/approve`, { method: "POST", body });
export const rejectRepair = (id, body) =>
  api(`/v1/repairs/${id}/reject`, { method: "POST", body });
export const rerunValidation = (id) =>
  api(`/v1/repairs/${id}/rerun-validation`, { method: "POST" });
export const publishPr = (id) =>
  api(`/v1/repairs/${id}/publish-pr`, { method: "POST" });
