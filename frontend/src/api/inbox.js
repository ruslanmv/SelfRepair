import { api, qs } from "./client.js";

export const listInbox = (params) => api(`/v1/inbox${qs(params)}`);
export const getInboxJob = (jobId) => api(`/v1/jobs/${jobId}`);
