export const DEFAULT_ORG_TIMEZONE = "Europe/Berlin";

export function sessionTimeZone(me: { auth_kind?: string; organization_timezone?: string } | null | undefined): string {
  if (me && me.auth_kind === "user" && me.organization_timezone) {
    return me.organization_timezone;
  }
  return DEFAULT_ORG_TIMEZONE;
}

type ZonedParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function zonedParts(instant: Date, timeZone: string): ZonedParts {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
  const parts = formatter.formatToParts(instant);
  const pick = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value ?? "0");
  let hour = pick("hour");
  if (hour === 24) {
    hour = 0;
  }
  return {
    year: pick("year"),
    month: pick("month"),
    day: pick("day"),
    hour,
    minute: pick("minute")
  };
}

export function localDateKey(iso: string, timeZone: string = DEFAULT_ORG_TIMEZONE): string {
  const parts = zonedParts(new Date(iso), timeZone);
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}`;
}

export function localHour(iso: string, timeZone: string = DEFAULT_ORG_TIMEZONE): number {
  return zonedParts(new Date(iso), timeZone).hour;
}

export function formatInstantTime(iso: string, timeZone: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23"
  }).format(new Date(iso));
}

export function toDatetimeLocalValue(iso: string, timeZone: string = DEFAULT_ORG_TIMEZONE): string {
  const parts = zonedParts(new Date(iso), timeZone);
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}`;
}

export function fromDatetimeLocalValue(value: string, timeZone: string = DEFAULT_ORG_TIMEZONE): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value);
  if (!match) {
    return new Date(value).toISOString();
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const desired = Date.UTC(year, month - 1, day, hour, minute);
  let utc = desired;
  for (let step = 0; step < 4; step += 1) {
    const parts = zonedParts(new Date(utc), timeZone);
    const shown = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute);
    const delta = desired - shown;
    if (delta === 0) {
      break;
    }
    utc += delta;
  }
  return new Date(utc).toISOString();
}
