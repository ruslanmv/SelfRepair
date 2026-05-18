import { useQuery } from "@tanstack/react-query";

import * as audit from "../api/audit.js";

export function useAudit(params) {
  return useQuery({
    queryKey: ["audit", params],
    queryFn: () => audit.listAudit(params),
    placeholderData: (prev) => prev,
  });
}

export function useAuditScope(scope, scopeId, params) {
  return useQuery({
    queryKey: ["audit-scope", scope, scopeId, params],
    queryFn: () => audit.listAuditScope(scope, scopeId, params),
    enabled: Boolean(scope && scopeId),
  });
}
