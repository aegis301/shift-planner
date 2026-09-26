import type { HoursLedger, HoursLedgerEntry, HoursLedgerTotals, TimeEntryReconciliationItem } from "@/lib/api/types";

export type { HoursLedger, HoursLedgerEntry, HoursLedgerTotals, TimeEntryReconciliationItem as HoursLedgerReconciliationItem } from "@/lib/api/types";

export type HoursLedgerEntryKind = HoursLedgerEntry["kind"];
export type HoursLedgerEntrySource = HoursLedgerEntry["source"];

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
  if ((entry.corrected_fields ?? []).includes(field)) {
    return true;
  }
  return derived !== entry[field];
}
