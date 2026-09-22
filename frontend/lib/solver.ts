import { apiFetch } from "@/lib/api";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

export type SolverRunStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type SolverObjectiveWeights = {
  unfilled: number;
  duty_count: number;
  fairness: number;
  wish: number;
  avoid_time_window: number;
  warning: number;
  pair_warning: number;
};

export type SolverConfigRead = {
  time_budget_ceiling_seconds: number;
  default_time_budget_seconds: number;
  weights: SolverObjectiveWeights;
};

export type SolverUnfilledSlot = {
  roster_slot_id: number;
  slot_date: string;
  label: string;
  binding_constraints: string[];
};

export type SolverPostCheckFinding = {
  code: string;
  severity: "info" | "warning" | "error";
  message: string;
  team_member_id: number | null;
  date: string | null;
  details: Record<string, unknown>;
};

export type SolverRunRead = {
  id: number;
  organization_id: number;
  planning_period_id: number;
  shift_group_id: number;
  status: SolverRunStatus;
  parameters: Record<string, unknown>;
  proposed_assignments: Array<{
    roster_slot_id: number;
    team_member_id: number;
    comment: string | null;
    manual_override: boolean;
  }>;
  objective_breakdown: Record<string, number>;
  unfilled_slots: SolverUnfilledSlot[];
  post_check_findings: SolverPostCheckFinding[];
  rule_set_version_id: number | null;
  failure_reason: string | null;
  cancel_requested: boolean;
  created_by_user_id: number | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  applied_at: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
};

export type SolverRunApplyRead = {
  run: SolverRunRead;
  assignments: unknown[];
};

export type SolverRunCreate = {
  shift_group_id: number;
  time_budget_seconds?: number;
  overwrite_existing?: boolean;
  objective_weights?: Partial<SolverObjectiveWeights>;
};

export const SOLVER_FORM_WEIGHT_KEYS = [
  "unfilled",
  "duty_count",
  "fairness",
  "wish",
  "avoid_time_window"
] as const;

export type SolverFormWeightKey = (typeof SOLVER_FORM_WEIGHT_KEYS)[number];

const WEIGHT_LABELS: Record<SolverFormWeightKey, TranslationKey> = {
  unfilled: "solverObjectiveUnfilled",
  duty_count: "solverObjectiveDutyCount",
  fairness: "solverObjectiveFairness",
  wish: "solverObjectiveWish",
  avoid_time_window: "solverObjectiveAvoidTimeWindow"
};

const STATUS_LABELS: Record<SolverRunStatus, TranslationKey> = {
  queued: "solverStatusQueued",
  running: "solverStatusRunning",
  succeeded: "solverStatusSucceeded",
  failed: "solverStatusFailed",
  cancelled: "solverStatusCancelled"
};

export function solverWeightLabel(locale: Locale, key: string): string {
  if (key in WEIGHT_LABELS) {
    return t(locale, WEIGHT_LABELS[key as SolverFormWeightKey]);
  }
  return key;
}

export function solverStatusLabel(locale: Locale, status: SolverRunStatus): string {
  return t(locale, STATUS_LABELS[status]);
}

export function isSolverRunActive(status: SolverRunStatus): boolean {
  return status === "queued" || status === "running";
}

export function fetchSolverConfig(): Promise<SolverConfigRead> {
  return apiFetch<SolverConfigRead>("/api/v1/organization/solver-config");
}

export function createSolverRun(periodId: string, payload: SolverRunCreate): Promise<SolverRunRead> {
  return apiFetch<SolverRunRead>(`/api/v1/planning-periods/${periodId}/solver-runs`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getSolverRun(periodId: string, runId: number): Promise<SolverRunRead> {
  return apiFetch<SolverRunRead>(`/api/v1/planning-periods/${periodId}/solver-runs/${runId}`);
}

export function listSolverRuns(periodId: string, shiftGroupId: string): Promise<SolverRunRead[]> {
  return apiFetch<SolverRunRead[]>(
    `/api/v1/planning-periods/${periodId}/solver-runs?shift_group_id=${encodeURIComponent(shiftGroupId)}`
  );
}

export function cancelSolverRun(periodId: string, runId: number): Promise<SolverRunRead> {
  return apiFetch<SolverRunRead>(`/api/v1/planning-periods/${periodId}/solver-runs/${runId}/cancel`, {
    method: "POST"
  });
}

export function applySolverRun(periodId: string, runId: number): Promise<SolverRunApplyRead> {
  return apiFetch<SolverRunApplyRead>(`/api/v1/planning-periods/${periodId}/solver-runs/${runId}/apply`, {
    method: "POST"
  });
}
