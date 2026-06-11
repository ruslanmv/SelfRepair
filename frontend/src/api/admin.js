import { api, qs } from "./client.js";

export const getStats = () => api(`/v1/admin/stats`);

export const listUsers = (params) => api(`/v1/admin/users${qs(params)}`);

export const getUser = (id) => api(`/v1/admin/users/${id}`);

export const updateUser = (id, patch) =>
  api(`/v1/admin/users/${id}`, { method: "PATCH", body: patch });

export const sendReset = (id) =>
  api(`/v1/admin/users/${id}/send-reset`, { method: "POST", body: {} });

export const deleteUser = (id) =>
  api(`/v1/admin/users/${id}`, { method: "DELETE" });

export const listAuditAdmin = (params) => api(`/v1/admin/audit${qs(params)}`);
