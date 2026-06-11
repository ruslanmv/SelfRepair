import { useQuery } from "@tanstack/react-query";

import * as inbox from "../api/inbox.js";

export function useInbox(params) {
  return useQuery({
    queryKey: ["inbox", params],
    queryFn: () => inbox.listInbox(params),
    placeholderData: (prev) => prev,
    refetchInterval: 30000,
  });
}

export function useInboxJob(jobId) {
  return useQuery({
    queryKey: ["inbox-job", jobId],
    queryFn: () => inbox.getInboxJob(jobId),
    enabled: Boolean(jobId),
  });
}
