import type { QueryClient } from "@tanstack/react-query";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
        await apiClient.POST("/api/v1/roster-matrix/assignments/clear", {
          params: { query },
          body: { roster_slot_id: input.rosterSlotId }
        });
        return null;
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

export async function writeRosterBundle(client: QueryClient, scope: PlanningScope, matrix: RosterMatrix): Promise<void> {
  client.setQueryData<RosterBundle>(
    queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    { matrix, blocked: false }
  );
}
