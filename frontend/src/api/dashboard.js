import { api } from "./client.js";

export const getDashboard = () => api("/v1/dashboard");
