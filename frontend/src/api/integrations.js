import { api } from "./client.js";

export const listIntegrations = () => api("/v1/integrations");
export const getIntegration = (id) => api(`/v1/integrations/${id}`);
export const connectIntegration = (provider, body) =>
  api(`/v1/integrations/${provider}/connect`, { method: "POST", body });
export const disconnectIntegration = (id) =>
  api(`/v1/integrations/${id}`, { method: "DELETE" });
