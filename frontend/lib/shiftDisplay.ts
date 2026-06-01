import type { Locale } from "@/lib/i18n";

export function formatPlanningDate(locale: Locale, isoDate: string): string {
  return new Intl.DateTimeFormat(locale === "de" ? "de-DE" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(`${isoDate}T12:00:00`));
}

export function formatShiftTimeRange(startsAt: string | null, endsAt: string | null): string {
  if (!startsAt || !endsAt) {
    return "";
  }
  const parseDateAndTime = (value: string): { date: string; time: string } | null => {
    const match = value.match(/(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/);
    if (!match) {
      return null;
    }
    return { date: match[1], time: match[2] };
  };

  const startParts = parseDateAndTime(startsAt);
  const endParts = parseDateAndTime(endsAt);

  if (startParts && endParts) {
    const nextDay = startParts.date !== endParts.date ? " +1" : "";
    return `${startParts.time}–${endParts.time}${nextDay}`;
  }

  const start = new Date(startsAt);
  const end = new Date(endsAt);
  const startText = start.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const endText = end.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  const nextDay = start.toDateString() !== end.toDateString() ? " +1" : "";
  return `${startText}–${endText}${nextDay}`;
}
