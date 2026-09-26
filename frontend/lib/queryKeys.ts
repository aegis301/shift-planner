export type PlanningScope = {
  organizationId: number;
  periodId: string;
  shiftGroupId: string;
  teamMemberPortal: boolean;
};

export const queryKeys = {
  session: () => ["session"] as const,
  planningPeriods: (organizationId: number) => ["planning-periods", organizationId] as const,
  shiftGroups: (organizationId: number) => ["shift-groups", organizationId] as const,
  dayStatuses: (organizationId: number) => ["day-statuses", organizationId] as const,
  wishesMatrix: (organizationId: number, periodId: string, shiftGroupId: string, teamMemberPortal: boolean) =>
    ["wishes-matrix", organizationId, periodId, shiftGroupId, teamMemberPortal] as const,
  wishesMatrixVersion: (organizationId: number, periodId: string, versionId: number) =>
    ["wishes-matrix-version", organizationId, periodId, versionId] as const,
  rosterMatrix: (organizationId: number, periodId: string, shiftGroupId: string, teamMemberPortal: boolean) =>
    ["roster-matrix", organizationId, periodId, shiftGroupId, teamMemberPortal] as const,
  rosterMatrixVersion: (organizationId: number, periodId: string, versionId: number) =>
    ["roster-matrix-version", organizationId, periodId, versionId] as const,
  validation: (organizationId: number, periodId: string, shiftGroupId: string) =>
    ["validation", organizationId, periodId, shiftGroupId] as const,
  fairness: (organizationId: number, periodId: string, shiftGroupId: string) =>
    ["fairness", organizationId, periodId, shiftGroupId] as const,
  solverRuns: (organizationId: number, periodId: string, shiftGroupId: string) =>
    ["solver-runs", organizationId, periodId, shiftGroupId] as const,
  shiftSwaps: (organizationId: number, periodId: string, shiftGroupId: string, scope: string) =>
    ["shift-swaps", organizationId, periodId, shiftGroupId, scope] as const,
  planVersions: (organizationId: number, periodId: string, shiftGroupId: string) =>
    ["plan-versions", organizationId, periodId, shiftGroupId] as const,
  memberDashboard: (organizationId: number, year: number, shiftGroupId: string) =>
    ["member-dashboard", organizationId, year, shiftGroupId] as const,
  complianceReport: (organizationId: number, periodId: string, shiftGroupId: string) =>
    ["compliance-report", organizationId, periodId, shiftGroupId] as const,
  dutyUtilization: (organizationId: number, rosterSlotId: number) =>
    ["duty-utilization", organizationId, rosterSlotId] as const,
  solverConfig: (organizationId: number) => ["solver-config", organizationId] as const
};
