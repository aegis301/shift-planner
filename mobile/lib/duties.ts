import type { MemberDutyRead } from "@shift-planner/api-client";
import { formatInstantTime, localDateKey } from "@shift-planner/domain";
import type { Locale } from "@shift-planner/i18n";

export type DutyWeek = {
  key: string;
  weekStart: string;
  data: MemberDutyRead[];
};

const DAY_MS = 86_400_000;

function utcDate(dateKey: string): Date {
  return new Date(`${dateKey}T00:00:00Z`);
}

function dateKeyOf(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addDays(dateKey: string, days: number): string {
  return dateKeyOf(new Date(utcDate(dateKey).getTime() + days * DAY_MS));
}

export function weekStartOf(dateKey: string): string {
  const weekday = (utcDate(dateKey).getUTCDay() + 6) % 7;
  return addDays(dateKey, -weekday);
}

export function windowAround(today: string): { from: string; to: string } {
  return { from: addDays(today, -7), to: addDays(today, 60) };
}

export function dutyWindow(now: Date, timeZone: string): { from: string; to: string } {
  return windowAround(localDateKey(now.toISOString(), timeZone));
}

export function groupDutiesByWeek(duties: readonly MemberDutyRead[]): DutyWeek[] {
  const sorted = [...duties].sort(
    (left, right) =>
      left.slot_date.localeCompare(right.slot_date) ||
      (left.starts_at ?? "").localeCompare(right.starts_at ?? "") ||
      left.roster_slot_id - right.roster_slot_id
  );
  const weeks = new Map<string, DutyWeek>();
  for (const duty of sorted) {
    const weekStart = weekStartOf(duty.slot_date);
    const week = weeks.get(weekStart) ?? { key: weekStart, weekStart, data: [] };
    week.data.push(duty);
    weeks.set(weekStart, week);
  }
  return [...weeks.values()];
}

function intlLocale(locale: Locale): string {
  return locale === "de" ? "de-DE" : "en-GB";
}

export function formatDutyDate(dateKey: string, locale: Locale): string {
  return new Intl.DateTimeFormat(intlLocale(locale), {
    timeZone: "UTC",
    weekday: "short",
    day: "2-digit",
    month: "2-digit"
  }).format(utcDate(dateKey));
}

export function formatDutyTimes(duty: Pick<MemberDutyRead, "starts_at" | "ends_at">, timeZone: string, locale: Locale): string {
  if (!duty.starts_at || !duty.ends_at) {
    return "";
  }
  const tag = intlLocale(locale);
  return `${formatInstantTime(duty.starts_at, timeZone, tag)}–${formatInstantTime(duty.ends_at, timeZone, tag)}`;
}

export function dutyTitle(duty: Pick<MemberDutyRead, "template_name" | "template_code" | "variant_label">): string {
  const base = duty.template_name || duty.template_code || "";
  return duty.variant_label ? `${base} · ${duty.variant_label}` : base;
}
