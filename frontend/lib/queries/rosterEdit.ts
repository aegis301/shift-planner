import type { QueryClient } from "@tanstack/react-query";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { queryKeys, type PlanningScope } from "@/lib/queryKeys";
import { invalidateQueryKeys, rosterAssignmentKeys } from "@/lib/queries/invalidation";
import type { RosterBundle } from "@/lib/queries/planning";
import { shiftGroupQuery } from "@/lib/queries/read";

type Assignment = components["schemas"]["RosterSlotAssignmentRead"];
type RosterMatrix = components["schemas"]["RosterMatrixRead"];

export function rosterMatrixWithAssignment(
  matrix: RosterMatrix,
  rosterSlotId: number,
  assignment: Assignment | null
): RosterMatrix {
  const rest = matrix.assignments.filter((row) => row.roster_slot_id !== rosterSlotId);
  return {
    ...matrix,
    assignments: assignment ? [...rest, assignment] : rest
  };
}

function optimisticAssignment(
  rosterSlotId: number,
  teamMemberId: number,
  manualOverride: boolean,
  previous: Assignment | undefined
): Assignment {
  const now = new Date().toISOString();
  return {
    id: previous?.id ?? -1,
    roster_slot_id: rosterSlotId,
    team_member_id: teamMemberId,
    manual_override: manualOverride,
    comment: null,
    source: previous?.source ?? "manual",
    created_at: previous?.created_at ?? now,
    updated_at: now
  };
}

export function useRosterAssignmentMutation(scope: PlanningScope | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { rosterSlotId: number; teamMemberId: number | ""; manualOverride: boolean }) => {
      if (!scope) {
        throw new ApiError(400, "Missing planning scope", null);
      }
      const query = shiftGroupQuery(scope.shiftGroupId);
      if (input.teamMemberId === "") {
        return (
          await apiClient.POST("/api/v1/roster-matrix/assignments/clear", {
            params: { query },
            body: { roster_slot_id: input.rosterSlotId }
          })
        ).data ?? null;
      }
      return await (
        await apiClient.PUT("/api/v1/roster-matrix/assignments", {
          params: { query },
          body: {
            roster_slot_id: input.rosterSlotId,
            team_member_id: input.teamMemberId,
            comment: null,
            manual_override: input.manualOverride
          }
        })
      ).data;
    },
    onMutate: async (input) => {
      if (!scope || scope.teamMemberPortal) {
        return { previous: undefined as RosterBundle | undefined };
      }
      const key = queryKeys.rosterMatrix(
        scope.organizationId,
        scope.periodId,
        scope.shiftGroupId,
        scope.teamMemberPortal
      );
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<RosterBundle>(key);
      if (previous?.matrix) {
        const current = previous.matrix.assignments.find((row) => row.roster_slot_id === input.rosterSlotId);
        const nextAssignment =
          input.teamMemberId === ""
            ? null
            : optimisticAssignment(input.rosterSlotId, input.teamMemberId, input.manualOverride, current);
        queryClient.setQueryData<RosterBundle>(key, {
          matrix: rosterMatrixWithAssignment(previous.matrix, input.rosterSlotId, nextAssignment),
          blocked: false
        });
      }
      return { previous };
    },
    onError: (_error, _input, context) => {
      if (!scope) {
        return;
      }
      const key = queryKeys.rosterMatrix(
        scope.organizationId,
        scope.periodId,
        scope.shiftGroupId,
        scope.teamMemberPortal
      );
      if (context?.previous) {
        queryClient.setQueryData(key, context.previous);
      }
    },
    onSettled: async () => {
      if (!scope) {
        return;
      }
      await invalidateQueryKeys(queryClient, rosterAssignmentKeys(scope));
    }
  });
}

export type RosterChangeSetRead = components["schemas"]["RosterChangeSetRead"];

export type RosterChangeWrite = {
  rosterSlotId: number;
  teamMemberId: number | null;
  manualOverride?: boolean;
};

export function rosterMatrixWithMemberUpdates(matrix: RosterMatrix, updates: RosterChangeWrite[]): RosterMatrix {
  return updates.reduce((current, update) => {
    if (update.teamMemberId == null) {
      return rosterMatrixWithAssignment(current, update.rosterSlotId, null);
    }
    const previous = current.assignments.find((row) => row.roster_slot_id === update.rosterSlotId);
    return rosterMatrixWithAssignment(
      current,
      update.rosterSlotId,
      optimisticAssignment(update.rosterSlotId, update.teamMemberId, update.manualOverride ?? false, previous)
    );
  }, matrix);
}

export function isRosterChangeSet(value: unknown): value is RosterChangeSetRead {
  if (!value || typeof value !== "object") {
    return false;
  }
  return "status" in value && "items" in value && Array.isArray((value as { items: unknown }).items);
}

export function useRosterChangeSetMutation(scope: PlanningScope | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { mode: "all_or_nothing" | "best_effort"; label?: string; items: RosterChangeWrite[] }) => {
      if (!scope) {
        throw new ApiError(400, "Missing planning scope", null);
      }
      try {
        const response = await apiClient.POST("/api/v1/roster-matrix/{planning_period_id}/change-sets", {
          params: {
            path: { planning_period_id: Number(scope.periodId) },
            query: { shift_group_id: Number(scope.shiftGroupId) }
          },
          body: {
            mode: input.mode,
            label: input.label,
            items: input.items.map((item) => ({
              roster_slot_id: item.rosterSlotId,
              team_member_id: item.teamMemberId,
              manual_override: item.manualOverride ?? false
            }))
          }
        });
        return { applied: true as const, changeSet: response.data as RosterChangeSetRead };
      } catch (error) {
        if (error instanceof ApiError && error.status === 409 && isRosterChangeSet(error.detail)) {
          return { applied: false as const, changeSet: error.detail };
        }
        throw error;
      }
    },
    onMutate: async (input) => {
      if (!scope || scope.teamMemberPortal) {
        return { previous: undefined as RosterBundle | undefined };
      }
      const key = queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<RosterBundle>(key);
      if (previous?.matrix) {
        queryClient.setQueryData<RosterBundle>(key, {
          matrix: rosterMatrixWithMemberUpdates(previous.matrix, input.items),
          blocked: false
        });
      }
      return { previous };
    },
    onSuccess: (result, _input, context) => {
      if (!scope || result.applied || !context?.previous) {
        return;
      }
      queryClient.setQueryData(
        queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
        context.previous
      );
    },
    onError: (_error, _input, context) => {
      if (!scope || !context?.previous) {
        return;
      }
      queryClient.setQueryData(
        queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
        context.previous
      );
    },
    onSettled: async () => {
      if (!scope) {
        return;
      }
      await invalidateQueryKeys(queryClient, rosterAssignmentKeys(scope));
    }
  });
}

export async function revertRosterChangeSet(changeSetId: number): Promise<{ applied: boolean; changeSet: RosterChangeSetRead }> {
  try {
    const response = await apiClient.POST("/api/v1/roster-matrix/change-sets/{change_set_id}/revert", {
      params: { path: { change_set_id: changeSetId } }
    });
    return { applied: true, changeSet: response.data as RosterChangeSetRead };
  } catch (error) {
    if (error instanceof ApiError && error.status === 409 && isRosterChangeSet(error.detail)) {
      return { applied: false, changeSet: error.detail };
    }
    throw error;
  }
}

export function useRosterChangeSets(scope: PlanningScope | null) {
  return useQuery({
    queryKey: queryKeys.rosterChangeSets(scope?.organizationId ?? 0, scope?.periodId ?? "", scope?.shiftGroupId ?? ""),
    enabled: scope != null && scope.periodId !== "" && scope.shiftGroupId !== "",
    queryFn: async () => {
      const response = await apiClient.GET("/api/v1/roster-matrix/{planning_period_id}/change-sets", {
        params: {
          path: { planning_period_id: Number(scope?.periodId) },
          query: { shift_group_id: Number(scope?.shiftGroupId), limit: 50 }
        }
      });
      return response.data ?? [];
    }
  });
}

export async function writeRosterBundle(client: QueryClient, scope: PlanningScope, matrix: RosterMatrix): Promise<void> {
  client.setQueryData<RosterBundle>(
    queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    { matrix, blocked: false }
  );
}
