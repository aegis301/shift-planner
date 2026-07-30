export type PatternWeekday = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

type SlotTimeSource = {
  slot_date: string;
  starts_at?: string | null;
  ends_at?: string | null;
  end_day_offset?: number | null;
};

function parseTimeParts(value: string): { hours: number; minutes: number } | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(value.trim());
  if (!match) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return null;
  }
  return { hours, minutes };
}

export function inferEndDayOffset(startsAt: string, endsAt: string): number {
  const start = parseTimeParts(startsAt);
  const end = parseTimeParts(endsAt);
  if (!start || !end) {
    return 0;
  }
  if (end.hours < start.hours || (end.hours === start.hours && end.minutes <= start.minutes)) {
    return 1;
  }
  return 0;
}

function addDays(isoDate: string, days: number): string {
  const base = new Date(`${isoDate}T12:00:00`);
  base.setDate(base.getDate() + days);
  return base.toISOString().slice(0, 10);
}

export function overlapCalendarDaysForSlot(slot: SlotTimeSource): string[] {
  const startDay = slot.slot_date;
  if (!startDay) {
    return [];
  }
  let endDay = startDay;
  if (slot.starts_at && slot.ends_at) {
    const offset =
      slot.end_day_offset != null && slot.end_day_offset >= 0
        ? slot.end_day_offset
        : inferEndDayOffset(slot.starts_at, slot.ends_at);
    endDay = addDays(startDay, offset);
  }
  const out: string[] = [];
  let cursor = startDay;
  while (cursor <= endDay) {
    out.push(cursor);
    cursor = addDays(cursor, 1);
  }
  return out;
}
