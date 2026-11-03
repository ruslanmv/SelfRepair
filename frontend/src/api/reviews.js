import { api, qs } from "./client.js";

// `/v1/reviews` — code reviews of pushes, pull requests and merge requests.
export const listReviews = (params) => api(`/v1/reviews${qs(params)}`);
export const getReview = (id) => api(`/v1/reviews/${id}`);
export const listReviewFindings = (id) => api(`/v1/reviews/${id}/findings`);
export const retryReview = (id) => api(`/v1/reviews/${id}/retry`, { method: "POST" });
export const listRemediations = (id) => api(`/v1/reviews/${id}/remediations`);
export const requestRemediation = (id, body) =>
  api(`/v1/reviews/${id}/remediations`, { method: "POST", body });
export const getOrgReviewSettings = () => api("/v1/review-settings");
export const putOrgReviewSettings = (config) =>
  api("/v1/review-settings", { method: "PUT", body: { config } });
