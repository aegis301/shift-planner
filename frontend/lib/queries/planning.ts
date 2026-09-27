import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { useSession } from "@/components/LocaleProvider";
import { isUserSession } from "@/lib/membershipRouting";
import { queryKeys } from "@/lib/queryKeys";
import { isQuietPlanningError, readData, shiftGroupQuery } from "@/lib/queries/read";

type Schemas = components["schemas"];

export type WishesBundle = {
  matrix: Schemas["PlanningMatrixRead"];
  notes: Schemas["TeamMemberPeriodNoteRead"][];
};

export type RosterBundle = {
  matrix: Schemas["RosterMatrixRead"] | null;
  blocked: boolean;
};

export type FairnessBundle = {
  accounts: Schemas["FairnessAccountsRead"] | null;
};

function useOrganizationId(): number | null {
  const { me } = useSession();
  if (!me || !isUserSession(me)) {
    return null;
  }
  return me.organization_id;
}

export function usePlanningOrganizationId(): number | null {
  return useOrganizationId();
}

function periodNumber(periodId: string): number {
  return Number(periodId);
}

export function usePlanningPeriods(enabled: boolean) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.planningPeriods(organizationId ?? 0),
    enabled: enabled && organizationId != null,
    queryFn: async () => readData(await apiClient.GET("/api/v1/planning-periods"))
  });
}

export function useShiftGroups(enabled: boolean) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.shiftGroups(organizationId ?? 0),
    enabled: enabled && organizationId != null,
    queryFn: async () =>
      readData(await apiClient.GET("/api/v1/shift-groups", { params: { query: { active_only: true } } }))
  });
}

export function useDayStatusDefinitions(enabled: boolean) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.dayStatuses(organizationId ?? 0),
    enabled: enabled && organizationId != null,
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/planning-day-status-definitions", {
          params: { query: { active_only: true } }
        })
      )
  });
}

export function useWishesMatrix(args: {
  periodId: string;
  shiftGroupId: string;
  teamMemberPortal: boolean;
  versionId?: number | null;
  enabled?: boolean;
}) {
  const organizationId = useOrganizationId();
  const versionId = args.versionId ?? null;
  const enabled = (args.enabled ?? true) && organizationId != null && args.periodId !== "";
  return useQuery({
    queryKey:
      versionId != null
        ? queryKeys.wishesMatrixVersion(organizationId ?? 0, args.periodId, versionId)
        : queryKeys.wishesMatrix(organizationId ?? 0, args.periodId, args.shiftGroupId, args.teamMemberPortal),
    enabled,
    queryFn: async (): Promise<WishesBundle> => {
      const periodId = periodNumber(args.periodId);
      if (versionId != null) {
        const matrix = await readData(
          await apiClient.GET("/api/v1/planning-periods/{planning_period_id}/versions/{version_id}/matrix", {
            params: { path: { planning_period_id: periodId, version_id: versionId } }
          })
        );
        return { matrix, notes: [] };
      }
      const query = {
        ...shiftGroupQuery(args.shiftGroupId),
        ...(args.teamMemberPortal ? { team_member_portal: true } : {})
      };
      const [matrix, notes] = await Promise.all([
        readData(
          await apiClient.GET("/api/v1/matrix/{planning_period_id}", {
            params: { path: { planning_period_id: periodId }, query }
          })
        ),
        readData(
          await apiClient.GET("/api/v1/matrix/{planning_period_id}/notes", {
            params: { path: { planning_period_id: periodId }, query }
          })
        )
      ]);
      return { matrix, notes };
    }
  });
}

export function useRosterMatrix(args: {
  periodId: string;
  shiftGroupId: string;
  teamMemberPortal: boolean;
  versionId?: number | null;
  enabled?: boolean;
}) {
  const organizationId = useOrganizationId();
  const versionId = args.versionId ?? null;
  const enabled = (args.enabled ?? true) && organizationId != null && args.periodId !== "";
  return useQuery({
    queryKey:
      versionId != null
        ? queryKeys.rosterMatrixVersion(organizationId ?? 0, args.periodId, versionId)
        : queryKeys.rosterMatrix(organizationId ?? 0, args.periodId, args.shiftGroupId, args.teamMemberPortal),
    enabled,
    queryFn: async (): Promise<RosterBundle> => {
      const periodId = periodNumber(args.periodId);
      try {
        if (versionId != null) {
          const matrix = await readData(
            await apiClient.GET("/api/v1/planning-periods/{planning_period_id}/versions/{version_id}/roster-matrix", {
              params: { path: { planning_period_id: periodId, version_id: versionId } }
            })
          );
          return { matrix, blocked: false };
        }
        const matrix = await readData(
          await apiClient.GET("/api/v1/roster-matrix/{planning_period_id}", {
            params: {
              path: { planning_period_id: periodId },
              query: {
                ...shiftGroupQuery(args.shiftGroupId),
                ...(args.teamMemberPortal ? { team_member_portal: true } : {})
              }
            }
          })
        );
        return { matrix, blocked: false };
      } catch (error) {
        if (isQuietPlanningError(error)) {
          return { matrix: null, blocked: true };
        }
        throw error;
      }
    }
  });
}

export function useValidation(args: { periodId: string; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.validation(organizationId ?? 0, args.periodId, args.shiftGroupId),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/validation/{planning_period_id}", {
          params: {
            path: { planning_period_id: periodNumber(args.periodId) },
            query: shiftGroupQuery(args.shiftGroupId)
          }
        })
      )
  });
}

export function useFairness(args: { periodId: string; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.fairness(organizationId ?? 0, args.periodId, args.shiftGroupId),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "",
    queryFn: async (): Promise<FairnessBundle> => {
      try {
        const accounts = await readData(
          await apiClient.GET("/api/v1/fairness/{planning_period_id}", {
            params: {
              path: { planning_period_id: periodNumber(args.periodId) },
              query: shiftGroupQuery(args.shiftGroupId)
            }
          })
        );
        return { accounts };
      } catch (error) {
        if (isQuietPlanningError(error)) {
          return { accounts: null };
        }
        throw error;
      }
    }
  });
}

export function useMemberDashboard(args: { year: number; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.memberDashboard(organizationId ?? 0, args.year, args.shiftGroupId),
    enabled: (args.enabled ?? true) && organizationId != null && args.shiftGroupId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/dashboard/team-member", {
          params: {
            query: {
              year: args.year,
              ...shiftGroupQuery(args.shiftGroupId)
            }
          }
        })
      )
  });
}

export function useComplianceReport(args: { periodId: string; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.complianceReport(organizationId ?? 0, args.periodId, args.shiftGroupId),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/compliance-report/{planning_period_id}", {
          params: {
            path: { planning_period_id: periodNumber(args.periodId) },
            query: shiftGroupQuery(args.shiftGroupId)
          }
        })
      )
  });
}

export function usePlanVersions(args: { periodId: string; shiftGroupId: string; enabled?: boolean }) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.planVersions(organizationId ?? 0, args.periodId, args.shiftGroupId),
    enabled: (args.enabled ?? true) && organizationId != null && args.periodId !== "" && args.shiftGroupId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/planning-periods/{planning_period_id}/versions", {
          params: {
            path: { planning_period_id: periodNumber(args.periodId) },
            query: { shift_group_id: Number(args.shiftGroupId) }
          }
        })
      )
  });
}

export function useDutyUtilization(rosterSlotId: number, enabled: boolean) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.dutyUtilization(organizationId ?? 0, rosterSlotId),
    enabled: enabled && organizationId != null,
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/duty-activity/slots/{roster_slot_id}/utilization", {
          params: { path: { roster_slot_id: rosterSlotId } }
        })
      )
  });
}

export function useSuggestedPlanVersion(args: {
  periodId: string;
  shiftGroupId: string;
  trigger: string;
  isMajorUpdate: boolean;
  enabled: boolean;
}) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: [
      "suggested-plan-version",
      organizationId ?? 0,
      args.periodId,
      args.shiftGroupId,
      args.trigger,
      args.isMajorUpdate
    ] as const,
    enabled: args.enabled && organizationId != null && args.periodId !== "" && args.shiftGroupId !== "",
    queryFn: async () =>
      readData(
        await apiClient.GET("/api/v1/planning-periods/{planning_period_id}/versions/suggest", {
          params: {
            path: { planning_period_id: periodNumber(args.periodId) },
            query: {
              shift_group_id: Number(args.shiftGroupId),
              trigger: args.trigger,
              is_major_update: args.isMajorUpdate
            }
          }
        })
      )
  });
}

export function useSolverConfig(enabled: boolean) {
  const organizationId = useOrganizationId();
  return useQuery({
    queryKey: queryKeys.solverConfig(organizationId ?? 0),
    enabled: enabled && organizationId != null,
    queryFn: async () => readData(await apiClient.GET("/api/v1/organization/solver-config"))
  });
}
