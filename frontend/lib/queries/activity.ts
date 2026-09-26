import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { queryKeys } from "@/lib/queryKeys";
import { solverPollInterval } from "@/lib/queries/invalidation";
import { usePlanningOrganizationId } from "@/lib/queries/planning";
import { readData } from "@/lib/queries/read";

export function useLatestSolverRun(args: { periodId: string; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = usePlanningOrganizationId();
  return useQuery({
    queryKey: queryKeys.solverRuns(organizationId ?? 0, args.periodId, args.shiftGroupId),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "" && args.shiftGroupId !== "",
    queryFn: async () => {
      const runs = await readData(
        await apiClient.GET("/api/v1/planning-periods/{planning_period_id}/solver-runs", {
          params: {
            path: { planning_period_id: Number(args.periodId) },
            query: { shift_group_id: Number(args.shiftGroupId) }
          }
        })
      );
      return runs[0] ?? null;
    },
    refetchInterval: (query) => solverPollInterval(query.state.data?.status)
  });
}

export function useShiftSwapList(args: {
  periodId: string;
  shiftGroupId: string;
  scope: string;
  statuses?: string[];
  enabled?: boolean;
}) {
  const organizationId = usePlanningOrganizationId();
  return useQuery({
    queryKey: queryKeys.shiftSwaps(organizationId ?? 0, args.periodId, args.shiftGroupId, args.scope),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "" && args.shiftGroupId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/shift-swaps", {
          params: {
            query: {
              planning_period_id: Number(args.periodId),
              shift_group_id: Number(args.shiftGroupId),
              ...(args.statuses ? { statuses: args.statuses } : {})
            }
          }
        })
      )
  });
}

export function useUnresolvedShiftSwaps(args: { periodId: string; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = usePlanningOrganizationId();
  return useQuery({
    queryKey: queryKeys.shiftSwaps(organizationId ?? 0, args.periodId, args.shiftGroupId, "unresolved"),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "" && args.shiftGroupId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/shift-swaps/unresolved", {
          params: {
            query: {
              planning_period_id: Number(args.periodId),
              shift_group_id: Number(args.shiftGroupId)
            }
          }
        })
      )
  });
}
