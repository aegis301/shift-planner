import type { Locale, TranslationKey } from "@/lib/i18n";

export type DutyActivityKind = "call_out" | "in_duty_activity";

export type DutyActivitySlotRef = {
  roster_slot_id: number;
  slot_date: string;
  starts_at: string | null;
  ends_at: string | null;
  category: string | null;
  template_name: string | null;
  template_code: string | null;
  variant_label: string | null;
};

export type DutyActivityEpisode = {
  id: number;
  roster_slot_id: number | null;
  kind: DutyActivityKind | string;
  started_at: string | null;
  ended_at: string | null;
  duration_minutes: number;
  reason: { code?: string | null; note?: string | null } | null;
};

export type DutyActivitySlotUtilization = {
  roster_slot_id: number;
  duty_minutes: number;
  worked_minutes: number;
  utilization_percent: string | number;
  band: "stufe_i" | "stufe_ii" | "full_work" | null;
  exceeds_on_call_threshold: boolean;
  has_activity_record: boolean;
};

export const DUTY_ACTIVITY_REASON_CODES = ["ward", "emergency", "other"] as const;

export function kindForCategory(category: string | null | undefined): DutyActivityKind | null {
  if (category === "rufdienst") {
    return "call_out";
  }
  if (category === "bereitschaftsdienst") {
    return "in_duty_activity";
  }
  return null;
}

export function isCapturableSlot(slot: DutyActivitySlotRef): boolean {
  return kindForCategory(slot.category) !== null && Boolean(slot.starts_at && slot.ends_at);
}

export function isSlotRunning(slot: DutyActivitySlotRef, now = new Date()): boolean {
  if (!slot.starts_at || !slot.ends_at) {
    return false;
  }
  const start = new Date(slot.starts_at);
  const end = new Date(slot.ends_at);
  return now >= start && now < end;
}

export function isSlotEnded(slot: DutyActivitySlotRef, now = new Date()): boolean {
  if (!slot.ends_at) {
    return false;
  }
  return now >= new Date(slot.ends_at);
}

export function runningCapturableSlot(slots: DutyActivitySlotRef[], now = new Date()): DutyActivitySlotRef | null {
  return slots.find((slot) => isCapturableSlot(slot) && isSlotRunning(slot, now)) ?? null;
}

export function slotTitle(slot: DutyActivitySlotRef): string {
  const base = slot.template_name ?? slot.template_code ?? "";
  return slot.variant_label ? `${base} · ${slot.variant_label}` : base;
}

export function toDatetimeLocalValue(iso: string): string {
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString();
}

export function utilizationPercentLabel(value: string | number): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return `${numeric.toLocaleString(undefined, { maximumFractionDigits: 1 })} %`;
}

export function bandLabelKey(band: DutyActivitySlotUtilization["band"]): TranslationKey {
  if (band === "stufe_ii") {
    return "dutyActivityBandStufeIi";
  }
  if (band === "full_work") {
    return "dutyActivityBandFullWork";
  }
  return "dutyActivityBandStufeI";
}

export function reasonLabelKey(code: string): TranslationKey {
  if (code === "emergency") {
    return "dutyActivityReasonEmergency";
  }
  if (code === "other") {
    return "dutyActivityReasonOther";
  }
  return "dutyActivityReasonWard";
}

export function formatMinutes(locale: Locale, minutes: number): string {
  return `${minutes.toLocaleString(locale === "de" ? "de-DE" : "en-GB")} min`;
}
