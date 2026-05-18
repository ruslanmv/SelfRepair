import { useQuery } from "@tanstack/react-query";

import * as dashboard from "../api/dashboard.js";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => dashboard.getDashboard(),
    refetchInterval: 30_000,
  });
}
