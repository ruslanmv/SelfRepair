import { api } from "./client.js";

export const login = (body) =>
  api("/v1/auth/login", { method: "POST", body });
export const logout = () => api("/v1/auth/logout", { method: "POST" });
export const refresh = () => api("/v1/auth/refresh", { method: "POST" });
export const me = () => api("/v1/me");
export const currentOrg = () => api("/v1/orgs/current");
