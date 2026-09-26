import type {
  FairnessAccountsRead,
  FairnessDimension,
  FairnessDimensionValue,
  FairnessMemberAccount,
  FairnessWindow
} from "@/lib/api/types";
import { slotTouchesWeekendOrNrwHoliday } from "@/lib/nrwCalendar";
import { t, type Locale } from "@/lib/i18n";
import { DEFAULT_ORG_TIMEZONE, localDateKey, localHour } from "@/lib/orgTime";

export type {
  FairnessAccountsRead,
  FairnessDimension,
  FairnessDimensionValue,
  FairnessMemberAccount,
  FairnessWindow
} from "@/lib/api/types";

export type FairnessMetric = FairnessDimension["metric"];
export type FairnessDayFilter = FairnessDimension["day_filter"];

export type FairnessSlotHint = {
  slot_date: string;
  starts_at?: string | null;
  ends_at?: string | null;
  day_class?: string | null;
  category?: string | null;
};

export type FairnessMemberIndex = Map<number, Map<string, FairnessDimensionValue>>;

const NIGHT_AFTER_HOUR = 21;

const KNOWN_DIMENSION_KEYS = {
  duties: "fairnessDimensionDuties",
  weekend_holiday: "fairnessDimensionWeekendHoliday",
  night: "fairnessDimensionNight",
  statutory_hours: "fairnessDimensionStatutoryHours"
} as const;

export function slotIsNightDuty(slot: FairnessSlotHint, timeZone: string = DEFAULT_ORG_TIMEZONE): boolean {
  if (slot.ends_at) {
    const endDay = localDateKey(slot.ends_at, timeZone);
    if (endDay > slot.slot_date) {
      return true;
    }
  }
  if (!slot.starts_at) {
    return false;
  }
  return localHour(slot.starts_at, timeZone) >= NIGHT_AFTER_HOUR;
}

export function slotIsWeekendOrHoliday(slot: FairnessSlotHint, timeZone: string = DEFAULT_ORG_TIMEZONE): boolean {
  if (slot.day_class === "weekend" || slot.day_class === "holiday") {
    return true;
  }
  return slotTouchesWeekendOrNrwHoliday(
    { slot_date: slot.slot_date, starts_at: slot.starts_at ?? null, ends_at: slot.ends_at ?? null },
    timeZone
  );
}

export function indexFairnessMembers(accounts: FairnessAccountsRead | null | undefined): FairnessMemberIndex {
  const index: FairnessMemberIndex = new Map();
  if (!accounts) {
    return index;
  }
  for (const member of accounts.members ?? []) {
    const byDimension = new Map<string, FairnessDimensionValue>();
    for (const value of member.dimensions ?? []) {
      byDimension.set(value.dimension_id, value);
    }
    index.set(member.team_member_id, byDimension);
  }
  return index;
}

function dimensionMatchScore(slot: FairnessSlotHint, dimension: FairnessDimension, night: boolean, weekend: boolean): number {
  if (dimension.metric === "statutory_minutes") {
    return -1;
  }
  if (dimension.night && !night) {
    return -1;
  }
  if (dimension.day_filter === "weekend_holiday" && !weekend) {
    return -1;
  }
  if (dimension.category && dimension.category !== slot.category) {
    return -1;
  }
  let score = 0;
  if (night && dimension.night) {
    score += 8;
  }
  if (weekend && dimension.day_filter === "weekend_holiday") {
    score += 4;
  }
  if (dimension.category && dimension.category === slot.category) {
    score += 2;
  }
  if (!dimension.night && dimension.day_filter === "any" && !dimension.category) {
    score += 1;
  }
  return score;
}

export function relevantFairnessDimension(
  slot: FairnessSlotHint,
  dimensions: FairnessDimension[],
  timeZone: string = DEFAULT_ORG_TIMEZONE
): FairnessDimension | undefined {
  const night = slotIsNightDuty(slot, timeZone);
  const weekend = slotIsWeekendOrHoliday(slot, timeZone);
  let best: FairnessDimension | undefined;
  let bestScore = 0;
  for (const dimension of dimensions) {
    const score = dimensionMatchScore(slot, dimension, night, weekend);
    if (score > bestScore) {
      bestScore = score;
      best = dimension;
    }
  }
  if (best) {
    return best;
  }
  return (
    dimensions.find((row) => row.id === "duties") ??
    dimensions.find((row) => row.metric === "duty_count" && !row.night && row.day_filter === "any" && !row.category)
  );
}

export function formatFairnessWindowRange(window: FairnessWindow): string {
  const start = `${window.start_year}-${String(window.start_month).padStart(2, "0")}`;
  const end = `${window.end_year}-${String(window.end_month).padStart(2, "0")}`;
  return `${start} – ${end}`;
}

export function fairnessDimensionLabel(locale: Locale, dimension: FairnessDimension): string {
  const key = KNOWN_DIMENSION_KEYS[dimension.id as keyof typeof KNOWN_DIMENSION_KEYS];
  if (key) {
    return t(locale, key);
  }
  return dimension.id;
}

function quantityLocale(locale: Locale): string {
  return locale === "de" ? "de-DE" : "en-US";
}

export function formatFairnessQuantity(value: number, metric: FairnessMetric, locale: Locale): string {
  const abs = Math.abs(value);
  if (metric === "statutory_minutes") {
    const hours = abs / 60;
    return `${hours.toLocaleString(quantityLocale(locale), { maximumFractionDigits: 1 })} h`;
  }
  return abs.toLocaleString(quantityLocale(locale), { maximumFractionDigits: 1 });
}

export function formatFairnessDeviation(value: number, metric: FairnessMetric, locale: Locale): string {
  const quantity = formatFairnessQuantity(value, metric, locale);
  if (value > 0.049) {
    return `+${quantity}`;
  }
  if (value < -0.049) {
    return `−${quantity}`;
  }
  return quantity;
}

export function fairnessDeviationTone(value: number): "under" | "over" | "even" {
  if (value <= -0.05) {
    return "under";
  }
  if (value >= 0.05) {
    return "over";
  }
  return "even";
}

export function fairnessDeviationChipClass(value: number): string {
  const tone = fairnessDeviationTone(value);
  if (tone === "under") {
    return "bg-teal-50 text-teal-900 ring-teal-200";
  }
  if (tone === "over") {
    return "bg-amber-50 text-amber-950 ring-amber-200";
  }
  return "bg-slate-50 text-slate-600 ring-slate-200";
}

export function fairnessValueForMember(
  index: FairnessMemberIndex,
  teamMemberId: number,
  dimensionId: string
): FairnessDimensionValue | undefined {
  return index.get(teamMemberId)?.get(dimensionId);
}
