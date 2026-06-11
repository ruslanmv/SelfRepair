import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as notifications from "../api/notifications.js";

export function useNotifications(params) {
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => notifications.listNotifications(params),
    placeholderData: (prev) => prev,
    // Poll so the bell reflects new control-plane requests without a reload.
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
    retry: false,
    // A transient notifications error must never crash the console.
    throwOnError: false,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => notifications.markNotificationRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => notifications.markAllNotificationsRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
