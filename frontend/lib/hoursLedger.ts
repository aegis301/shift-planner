export type HoursLedgerEntryKind = "work" | "absence" | "call_out" | "in_duty_activity";
export type HoursLedgerEntrySource = "roster" | "day_status" | "manual";

export type HoursLedgerEntry = {
  id: number;
  organization_id: number;
  team_member_id: number;
  entry_date: string;
  kind: HoursLedgerEntryKind;
  source: HoursLedgerEntrySource;
  all_day: boolean;
  started_at: string | null;
  ended_at: string | null;
  duration_minutes: number;
  statutory_minutes: number;
  credited_minutes: number;
  counts_toward_contract: boolean;
  consumes_vacation: boolean;
  shift_template_category: string | null;
  planning_day_status_code: string | null;
  roster_slot_id: number | null;
  shift_group_id: number | null;
  comment: string | null;
  derived_snapshot: Record<string, unknown> | null;
  corrected_fields: string[];
};

export type HoursLedgerReconciliationItem = {
  id: number;
  team_member_id: number;
  entry_date: string;
  source: HoursLedgerEntrySource;
  derived: Record<string, unknown> | null;
  effective: HoursLedgerEntry;
  corrected_fields: string[];
  diverges: boolean;
};

export type HoursLedgerTotals = {
  contract_target_minutes: number;
  statutory_minutes: number;
  credited_minutes: number;
  credited_minutes_toward_contract: number;
  absence_count: number;
  vacation_days_consumed: string;
  opening_overtime_minutes: number;
  running_overtime_minutes: number;
  vacation_days_remaining: string | null;
};

export type HoursLedger = {
  team_member_id: number;
  start_date: string;
  end_date: string;
  opening: {
    team_member_id: number;
    as_of_date: string;
    overtime_minutes: number;
    vacation_days_remaining: string;
    sick_days_used_ytd: string;
  } | null;
  totals: HoursLedgerTotals;
  entries: HoursLedgerEntry[];
  reconciliation: HoursLedgerReconciliationItem[];
};

export function formatLedgerMinutes(minutes: number): string {
  const sign = minutes < 0 ? "-" : "";
  const abs = Math.abs(Math.trunc(minutes));
  const hours = Math.floor(abs / 60);
  const rest = abs % 60;
  return `${sign}${hours}:${String(rest).padStart(2, "0")}`;
}

export function snapshotNumber(snapshot: Record<string, unknown> | null | undefined, field: string): number | null {
  if (!snapshot || !(field in snapshot)) {
    return null;
  }
  const value = snapshot[field];
  return typeof value === "number" ? value : null;
}

export function shouldShowDerived(entry: HoursLedgerEntry, field: keyof HoursLedgerEntry): boolean {
  if (entry.source === "manual") {
    return false;
  }
  const derived = snapshotNumber(entry.derived_snapshot, field);
  if (derived == null) {
    return false;
  }
  if (entry.corrected_fields.includes(field)) {
    return true;
  }
  return derived !== entry[field];
}
