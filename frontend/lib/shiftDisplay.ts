import type { Locale } from "@/lib/i18n";
import { DEFAULT_ORG_TIMEZONE, formatInstantTime, localDateKey } from "@/lib/orgTime";

export function formatPlanningDate(locale: Locale, isoDate: string): string {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(`${isoDate}T12:00:00`));
}

export function formatShiftTimeRange(
  startsAt: string | null,
  endsAt: string | null,
  timeZone: string = DEFAULT_ORG_TIMEZONE
): string {
  if (!startsAt || !endsAt) {
    return "";
  }
  const locale = "de-DE";
  const startText = formatInstantTime(startsAt, timeZone, locale);
  const endText = formatInstantTime(endsAt, timeZone, locale);
  const nextDay = localDateKey(startsAt, timeZone) !== localDateKey(endsAt, timeZone) ? " +1" : "";
  return `${startText}–${endText}${nextDay}`;
}
