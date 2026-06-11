import { api } from "./client.js";

export const listConnections = () => api("/v1/connections");

export const saveConnection = (provider, body) =>
  api(`/v1/connections/${provider}`, { method: "POST", body });

export const testConnection = (provider) =>
  api(`/v1/connections/${provider}/test`, { method: "POST" });
