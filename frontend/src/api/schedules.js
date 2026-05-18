import { api } from "./client.js";

export const listSchedules = () => api("/v1/schedules");
export const getSchedule = (id) => api(`/v1/schedules/${id}`);
export const createSchedule = (body) =>
  api("/v1/schedules", { method: "POST", body });
export const patchSchedule = (id, body) =>
  api(`/v1/schedules/${id}`, { method: "PATCH", body });
export const deleteSchedule = (id) =>
  api(`/v1/schedules/${id}`, { method: "DELETE" });
