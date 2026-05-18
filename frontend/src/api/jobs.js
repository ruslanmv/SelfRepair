import { api, qs } from "./client.js";

export const listJobs = (params) => api(`/v1/jobs${qs(params)}`);
export const getJob = (id) => api(`/v1/jobs/${id}`);
export const listJobEvents = (id, params) =>
  api(`/v1/jobs/${id}/events${qs(params)}`);
export const createJob = (body) =>
  api("/v1/jobs", { method: "POST", body });
export const cancelJob = (id) =>
  api(`/v1/jobs/${id}/cancel`, { method: "POST" });
export const retryJob = (id) =>
  api(`/v1/jobs/${id}/retry`, { method: "POST" });
