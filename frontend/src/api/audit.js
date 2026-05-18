import { api, qs } from "./client.js";

export const listAudit = (params) => api(`/v1/audit${qs(params)}`);
export const getAudit = (id) => api(`/v1/audit/${id}`);
export const listAuditScope = (scope, scopeId, params) =>
  api(`/v1/audit/scopes/${scope}/${scopeId}${qs(params)}`);
export const auditExportUrl = (params) => `/v1/audit/export${qs(params)}`;
