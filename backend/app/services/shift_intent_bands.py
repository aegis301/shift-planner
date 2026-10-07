"""Day/night bands for shift wishes and no-gos.

A slot is in the night band when it ends on a later local date than it starts or starts at
or after 14:00 local time. This is the split the roster grid's day/night view uses
(`frontend/lib/rosterColumns.ts`), so a wish for the night band matches the night column.
"""

from datetime import date, datetime
from typing import Literal

from app.services.org_time import DEFAULT_TIMEZONE, instant_to_local, local_date_of

ShiftIntentBand = Literal["all", "day", "night"]

NIGHT_BAND_FROM_HOUR = 14


def slot_band(
    starts_at: datetime | None,
    ends_at: datetime | None,
    tz: str = DEFAULT_TIMEZONE,
) -> Literal["day", "night"]:
    if starts_at is None or ends_at is None:
        return "day"
    if local_date_of(ends_at, tz) > local_date_of(starts_at, tz):
        return "night"
    if instant_to_local(starts_at, tz).hour >= NIGHT_BAND_FROM_HOUR:
        return "night"
    return "day"


def intent_band(intent: object) -> str:
    return getattr(intent, "band", None) or "all"


def intent_matches_slot(
    intent: object,
    *,
    team_member_id: int,
    slot_date: date,
    shift_template_id: int | None,
    band: str,
) -> bool:
    if intent.team_member_id != team_member_id:
        return False
    if intent.cell_date != slot_date:
        return False
    if shift_template_id is None or intent.shift_template_id != shift_template_id:
        return False
    wanted = intent_band(intent)
    return wanted == "all" or wanted == band


def roster_slot_band(slot: object, tz: str = DEFAULT_TIMEZONE) -> Literal["day", "night"]:
    return slot_band(getattr(slot, "starts_at", None), getattr(slot, "ends_at", None), tz)
