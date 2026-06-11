import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as admin from "../api/admin.js";

const QUERY_OPTS = { retry: false, throwOnError: false };

export function useAdminStats() {
  return useQuery({
    queryKey: ["admin", "stats"],
    queryFn: () => admin.getStats(),
    ...QUERY_OPTS,
  });
}

export function useAdminUsers(params) {
  return useQuery({
    queryKey: ["admin", "users", params],
    queryFn: () => admin.listUsers(params),
    placeholderData: (prev) => prev,
    ...QUERY_OPTS,
  });
}

export function useAdminUser(id) {
  return useQuery({
    queryKey: ["admin", "user", id],
    queryFn: () => admin.getUser(id),
    enabled: Boolean(id),
    ...QUERY_OPTS,
  });
}

export function useAdminAudit(params) {
  return useQuery({
    queryKey: ["admin", "audit", params],
    queryFn: () => admin.listAuditAdmin(params),
    placeholderData: (prev) => prev,
    ...QUERY_OPTS,
  });
}

function useInvalidateAdmin() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["admin"] });
  };
}

export function useUpdateUser() {
  const invalidate = useInvalidateAdmin();
  return useMutation({
    mutationFn: ({ id, patch }) => admin.updateUser(id, patch),
    throwOnError: false,
    onSuccess: invalidate,
  });
}

export function useSendReset() {
  const invalidate = useInvalidateAdmin();
  return useMutation({
    mutationFn: ({ id }) => admin.sendReset(id),
    throwOnError: false,
    onSuccess: invalidate,
  });
}

export function useDeleteUser() {
  const invalidate = useInvalidateAdmin();
  return useMutation({
    mutationFn: ({ id }) => admin.deleteUser(id),
    throwOnError: false,
    onSuccess: invalidate,
  });
}
