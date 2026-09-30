function padDatePart(value: number): string {
  return String(value).padStart(2, "0");
}

function toIsoDate(year: number, month: number, day: number): string {
  return `${year}-${padDatePart(month)}-${padDatePart(day)}`;
}

export function monthDateBounds(year: number, month: number): { min: string; max: string } {
  const lastDay = new Date(year, month, 0).getDate();
  return {
    min: toIsoDate(year, month, 1),
    max: toIsoDate(year, month, lastDay)
  };
}

export function todayIsoDate(): string {
  const now = new Date();
  return toIsoDate(now.getFullYear(), now.getMonth() + 1, now.getDate());
}

export function formatIsoDate(iso: string, locale: string): string {
  const parsed = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return iso;
  }
  return parsed.toLocaleDateString(locale === "de" ? "de-DE" : "en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric"
  });
}

export type DateRangeStatus = "active" | "ended" | "planned";

export function isoDateRangeStatus(
  startDate: string,
  endDate: string | null,
  onDate: string = todayIsoDate()
): DateRangeStatus {
  if (startDate > onDate) {
    return "planned";
  }
  if (endDate && endDate < onDate) {
    return "ended";
  }
  return "active";
}

export function isoDateRangesOverlap(
  firstStart: string,
  firstEnd: string | null,
  secondStart: string,
  secondEnd: string | null
): boolean {
  const firstStop = firstEnd ?? "9999-12-31";
  const secondStop = secondEnd ?? "9999-12-31";
  return firstStart <= secondStop && secondStart <= firstStop;
}

export function expandInclusiveDateRange(from: string, to: string): string[] {
  const start = new Date(`${from}T12:00:00`);
  const end = new Date(`${to}T12:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) {
    return [];
  }
  const dates: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    dates.push(
      toIsoDate(cursor.getFullYear(), cursor.getMonth() + 1, cursor.getDate())
    );
    cursor.setDate(cursor.getDate() + 1);
  }
  return dates;
}
