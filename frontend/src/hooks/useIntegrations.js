import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import * as integrations from "../api/integrations.js";

export function useIntegrations() {
  return useQuery({
    queryKey: ["integrations"],
    queryFn: () => integrations.listIntegrations(),
  });
}

export function useIntegration(id) {
  return useQuery({
    queryKey: ["integration", id],
    queryFn: () => integrations.getIntegration(id),
    enabled: Boolean(id),
  });
}

export function useConnectIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, body }) =>
      integrations.connectIntegration(provider, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations"] }),
  });
}

export function useDisconnectIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => integrations.disconnectIntegration(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["integrations"] }),
  });
}
