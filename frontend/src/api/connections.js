import { api } from "./client.js";

export const listConnections = () => api("/v1/connections");

export const saveConnection = (provider, body) =>
  api(`/v1/connections/${encodeURIComponent(provider)}`, { method: "POST", body });

export const testConnection = (provider) =>
  api(`/v1/connections/${encodeURIComponent(provider)}/test`, { method: "POST" });

export const disconnectConnection = (provider) =>
  api(`/v1/connections/${encodeURIComponent(provider)}`, { method: "DELETE" });

// Pair codes are exchanged server-to-server. The device token never crosses
// the browser boundary or appears in JSON returned to the SPA.
export const pairOllaBridge = (code) =>
  api("/v1/connections/ollabridge/pair", { method: "POST", body: { code } });
