import { apiFetch } from "@/lib/api";
import type {
  SolverConfigRead,
  SolverObjectiveWeights,
  SolverRunApplyRead,
  SolverRunCreate,
  SolverRunRead
} from "@/lib/api/types";
import { t, type Locale, type TranslationKey } from "@/lib/i18n";

export type {
  SolverConfigRead,
  SolverObjectiveWeights,
  SolverRunApplyRead,
  SolverRunCreate,
  SolverRunRead
} from "@/lib/api/types";

export type SolverRunStatus = SolverRunRead["status"];

export type SolverUnfilledSlotView = {
  roster_slot_id: number;
  slot_date: string;
  label: string;
  binding_constraints: string[];
};

export type SolverPostCheckFindingView = {
  code: string;
  severity: string;
  message: string;
  date: string | null;
};

function recordField(value: unknown, key: string): unknown {
  if (value && typeof value === "object" && key in value) {
    return (value as Record<string, unknown>)[key];
  }
  return undefined;
}

export function readUnfilledSlot(value: unknown, index: number): SolverUnfilledSlotView {
  const constraints = recordField(value, "binding_constraints");
  const rosterSlotId = recordField(value, "roster_slot_id");
  const slotDate = recordField(value, "slot_date");
  const label = recordField(value, "label");
  return {
    roster_slot_id: typeof rosterSlotId === "number" ? rosterSlotId : index,
    slot_date: typeof slotDate === "string" ? slotDate : "",
    label: typeof label === "string" ? label : "",
    binding_constraints: Array.isArray(constraints)
      ? constraints.filter((item): item is string => typeof item === "string")
      : []
  };
}

export function readPostCheckFinding(value: unknown): SolverPostCheckFindingView {
  const severity = recordField(value, "severity");
  const date = recordField(value, "date");
  const code = recordField(value, "code");
  const message = recordField(value, "message");
  return {
    code: typeof code === "string" ? code : "",
    severity: typeof severity === "string" ? severity : "info",
    message: typeof message === "string" ? message : "",
    date: typeof date === "string" ? date : null
  };
}

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
