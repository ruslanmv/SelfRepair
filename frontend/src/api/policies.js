import { api, qs } from "./client.js";

export const listPolicies = (params) => api(`/v1/policies${qs(params)}`);
export const getPolicy = (id) => api(`/v1/policies/${id}`);
export const uploadBundle = (body) =>
  api("/v1/policies/bundle", { method: "PUT", body });
export const evaluatePolicy = (body) =>
  api("/v1/policies/evaluate", { method: "POST", body });
export const listPolicyDecisions = (params) =>
  api(`/v1/policies/decisions${qs(params)}`);
