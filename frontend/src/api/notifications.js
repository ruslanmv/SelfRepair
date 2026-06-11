import { api, qs } from "./client.js";

export const listNotifications = (params) =>
  api(`/v1/notifications${qs(params)}`);
export const markNotificationRead = (id) =>
  api(`/v1/notifications/${id}/read`, { method: "POST" });
export const markAllNotificationsRead = () =>
  api("/v1/notifications/read-all", { method: "POST" });
