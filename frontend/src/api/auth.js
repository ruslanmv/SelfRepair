import { api } from "./client.js";

export const login = (body) =>
  api("/v1/auth/login", { method: "POST", body });
export const logout = () => api("/v1/auth/logout", { method: "POST" });
export const refresh = () => api("/v1/auth/refresh", { method: "POST" });
export const me = () => api("/v1/me");
export const currentOrg = () => api("/v1/orgs/current");

// Self-service auth flows (the SPA owns these now).
export const register = (body) =>
  api("/v1/auth/register", { method: "POST", body });
export const resendVerification = (email) =>
  api("/v1/auth/resend-verification", { method: "POST", body: { email } });
export const verifyEmail = (token) =>
  api("/v1/auth/verify", { method: "POST", body: { token } });
export const forgotPassword = (email) =>
  api("/v1/auth/forgot-password", { method: "POST", body: { email } });
export const resetPassword = (token, password) =>
  api("/v1/auth/reset-password", { method: "POST", body: { token, password } });
