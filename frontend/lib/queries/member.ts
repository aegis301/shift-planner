import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/queryKeys";
import { usePlanningOrganizationId } from "@/lib/queries/planning";
import { readData } from "@/lib/queries/read";

export function useMemberHome(enabled = true) {
  const organizationId = usePlanningOrganizationId();
  return useQuery({
    queryKey: queryKeys.memberHome(organizationId ?? 0),
    enabled: enabled && organizationId != null,
    queryFn: async () => readData(await apiClient.GET("/api/v1/me/home"))
  });
}

export function useMemberDuties(args: { from: string; to: string; enabled?: boolean }) {
  const organizationId = usePlanningOrganizationId();
  return useQuery({
    queryKey: queryKeys.memberDuties(organizationId ?? 0, args.from, args.to),
    enabled: (args.enabled ?? true) && organizationId != null && args.from !== "" && args.to !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/me/duties", {
          params: { query: { from: args.from, to: args.to } }
        })
      )
  });
}

export function useMemberSwaps(enabled = true) {
  const organizationId = usePlanningOrganizationId();
  return useQuery({
    queryKey: queryKeys.memberSwaps(organizationId ?? 0, ""),
    enabled: enabled && organizationId != null,
    queryFn: async () => readData(await apiClient.GET("/api/v1/me/swaps"))
  });
}
