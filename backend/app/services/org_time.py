from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, available_timezones

from sqlalchemy.orm import Session

DEFAULT_TIMEZONE = "Europe/Berlin"

_ZONES: frozenset[str] | None = None


def known_timezones() -> frozenset[str]:
    global _ZONES
    if _ZONES is None:
        _ZONES = frozenset(available_timezones())
    return _ZONES


def validate_timezone(value: str) -> str:
    name = value.strip()
    if name not in known_timezones():
        raise ValueError("Unknown time zone")
    return name


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def local_to_instant(day: date, clock: time, tz: str) -> datetime:
    local = datetime.combine(day, clock.replace(tzinfo=None), tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC)


def instant_to_local(value: datetime, tz: str) -> datetime:
    return as_utc(value).astimezone(ZoneInfo(tz))


def local_date_of(value: datetime, tz: str) -> date:
    return instant_to_local(value, tz).date()


def local_day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    start = local_to_instant(day, time.min, tz)
    end = local_to_instant(day + timedelta(days=1), time.min, tz)
    return start, end


def minutes_on_local_day(start: datetime, end: datetime, day: date, tz: str) -> int:
    day_start, day_end = local_day_bounds(day, tz)
    overlap_start = max(as_utc(start), day_start)
    overlap_end = min(as_utc(end), day_end)
    if overlap_end <= overlap_start:
        return 0
    return int((overlap_end - overlap_start).total_seconds() // 60)


def local_dates_spanned(start: datetime, end: datetime, tz: str) -> list[date]:
    first = local_date_of(start, tz)
    last = local_date_of(end, tz)
    out: list[date] = []
    day = first
    while day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out


def slot_bounds(
    slot_date: date,
    start_clock: time,
    end_clock: time,
    end_day_offset: int,
    tz: str,
) -> tuple[datetime, datetime]:
    end_date = slot_date + timedelta(days=end_day_offset)
    starts_at = local_to_instant(slot_date, start_clock, tz)
    ends_at = local_to_instant(end_date, end_clock, tz)
    if ends_at <= starts_at:
        ends_at = local_to_instant(end_date + timedelta(days=1), end_clock, tz)
    return starts_at, ends_at


def is_night_duty(
    entry_date: date,
    started_at: datetime | None,
    ended_at: datetime | None,
    tz: str,
) -> bool:
    if ended_at is not None and local_date_of(ended_at, tz) > entry_date:
        return True
    if started_at is None:
        return False
    return instant_to_local(started_at, tz).hour >= 21


def organization_timezone(db: Session | None, organization_id: int) -> str:
    from app.models import Organization

    if db is None:
        return DEFAULT_TIMEZONE
    org = db.get(Organization, organization_id)
    raw = getattr(org, "timezone", None) if org is not None else None
    if not raw:
        return DEFAULT_TIMEZONE
    return str(raw)


def timezone_for_slot(db: Session, slot: object) -> str:
    from app.models import PlanningPeriod

    period_id = getattr(slot, "planning_period_id", None)
    if period_id is None:
        return DEFAULT_TIMEZONE
    period = db.get(PlanningPeriod, period_id)
    organization_id = getattr(period, "organization_id", None)
    if organization_id is None:
        return DEFAULT_TIMEZONE
    return organization_timezone(db, int(organization_id))
