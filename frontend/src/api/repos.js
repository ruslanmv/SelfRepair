import { api, qs } from "./client.js";

export const listRepos = (params) => api(`/v1/repos${qs(params)}`);
export const getRepo = (id) => api(`/v1/repos/${id}`);
export const getRepoSummary = (id) => api(`/v1/repos/${id}/summary`);
export const getRepoConfig = (id) => api(`/v1/repos/${id}/config`);
export const syncRepos = (body) =>
  api("/v1/repos/sync", { method: "POST", body: body || {} });
