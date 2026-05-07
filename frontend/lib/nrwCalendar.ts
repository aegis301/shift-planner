function easterSundayYmd(year: number): { monthIndex0: number; day: number } {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const ell = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * ell) / 451);
  const monthNum = Math.floor((h + ell - 7 * m + 114) / 31);
  const day = ((h + ell - 7 * m + 114) % 31) + 1;
  return { monthIndex0: monthNum - 1, day };
}

const holidayCache = new Map<number, Set<string>>();

export function nrwPublicHolidayIsoDates(year: number): Set<string> {
  const cached = holidayCache.get(year);
  if (cached) {
    return cached;
  }
  const { monthIndex0, day } = easterSundayYmd(year);
  const easter = new Date(year, monthIndex0, day);
  const iso = (dt: Date) => {
    const yy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    return `${yy}-${mm}-${dd}`;
  };
  const shift = (dt: Date, n: number) => {
    const copy = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    copy.setDate(copy.getDate() + n);
    return copy;
  };
  const out = new Set<string>([
    `${year}-01-01`,
    `${year}-05-01`,
    `${year}-10-03`,
    `${year}-11-01`,
    `${year}-12-25`,
    `${year}-12-26`,
    iso(shift(easter, -2)),
    iso(shift(easter, 1)),
    iso(shift(easter, 39)),
    iso(shift(easter, 50)),
    iso(shift(easter, 60))
  ]);
  holidayCache.set(year, out);
  return out;
}

export function isWeekendOrNrwPublicHoliday(isoDate: string): boolean {
  const parts = isoDate.split("-").map(Number);
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) {
    return false;
  }
  const [y, m, d] = parts;
  const dt = new Date(y, m - 1, d);
  const wd = dt.getDay();
  if (wd === 0 || wd === 6) {
    return true;
  }
  return nrwPublicHolidayIsoDates(y).has(isoDate);
}

export function slotTouchesWeekendOrNrwHoliday(slot: {
  slot_date: string;
  starts_at: string | null;
  ends_at: string | null;
}): boolean {
  const fromIso = (value: string | null | undefined, fallback: string) => {
    if (!value) {
      return fallback;
    }
    const match = value.match(/^(\d{4}-\d{2}-\d{2})/);
    return match ? match[1] : fallback;
  };
  const start = fromIso(slot.starts_at, slot.slot_date);
  const end = fromIso(slot.ends_at, start);
  return isWeekendOrNrwPublicHoliday(start) || isWeekendOrNrwPublicHoliday(end);
}
