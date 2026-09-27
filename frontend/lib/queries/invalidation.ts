import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { queryKeys, type PlanningScope } from "@/lib/queryKeys";

export function rosterAssignmentKeys(scope: PlanningScope): QueryKey[] {
  return [
    queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    queryKeys.validation(scope.organizationId, scope.periodId, scope.shiftGroupId),
    queryKeys.fairness(scope.organizationId, scope.periodId, scope.shiftGroupId)
  ];
}

export function wishesEditKeys(scope: PlanningScope): QueryKey[] {
  return [
    queryKeys.wishesMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    queryKeys.validation(scope.organizationId, scope.periodId, scope.shiftGroupId)
  ];
}

export function statusTransitionKeys(scope: PlanningScope): QueryKey[] {
  return [
    queryKeys.wishesMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    queryKeys.rosterMatrix(scope.organizationId, scope.periodId, scope.shiftGroupId, scope.teamMemberPortal),
    queryKeys.planVersions(scope.organizationId, scope.periodId, scope.shiftGroupId),
    queryKeys.planningPeriods(scope.organizationId)
  ];
}

export async function invalidateQueryKeys(client: QueryClient, keys: QueryKey[]): Promise<void> {
  await Promise.all(keys.map((queryKey) => client.invalidateQueries({ queryKey })));
}

export function clearOrganizationCache(client: QueryClient): void {
  client.clear();
}

export function solverPollInterval(status: string | null | undefined, intervalMs = 1000): number | false {
  if (status === "queued" || status === "running") {
    return intervalMs;
  }
  return false;
}
