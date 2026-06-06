from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Organization, PlanningPeriod, RosterSlot, RosterSlotAssignment, ShiftGroup, ShiftGroupShiftTemplate
from app.services.dashboard import _scope_template_and_member_ids
from app.services.planning import get_shift_group_planning_status, is_team_member_roster_visible
from app.services.authz import team_member_shift_group_ids
from app.services.shift_groups import require_shift_group

ICS_UID_DOMAIN = "shift-planner.local"
DEFAULT_TZ = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class ShiftCalendarEvent:
    roster_slot_id: int
    slot_date: date
    starts_at: datetime | None
    ends_at: datetime | None
    all_day: bool
    summary: str
    description: str
    uid: str


def event_uid(*, organization_id: int, roster_slot_id: int) -> str:
    return f"shift-planner-{organization_id}-slot-{roster_slot_id}@{ICS_UID_DOMAIN}"


def _summary_for_slot(slot: RosterSlot) -> str:
    template = slot.shift_template
    variant = slot.shift_variant
    base = (template.name if template and template.name else None) or (
        template.code if template and template.code else None
    ) or slot.label or "Shift"
    if variant and variant.label:
        return f"{base} · {variant.label}"
    return base


def _description_lines(
    *,
    category: str | None,
    day_class: str | None,
    shift_group_name: str | None,
    organization_name: str | None,
) -> str:
    parts: list[str] = []
    if organization_name:
        parts.append(organization_name)
    if shift_group_name:
        parts.append(shift_group_name)
    if category:
        parts.append(f"Category: {category}")
    if day_class:
        parts.append(f"Day: {day_class}")
    return "\\n".join(parts)


def _combine_date_time(slot_date: date, clock: time, day_offset: int = 0) -> datetime:
    base = datetime.combine(slot_date, clock, tzinfo=DEFAULT_TZ)
    if day_offset:
        base += timedelta(days=day_offset)
    return base


def _resolve_event_times(slot: RosterSlot) -> tuple[datetime | None, datetime | None, bool]:
    if slot.starts_at is not None and slot.ends_at is not None:
        start = slot.starts_at
        end = slot.ends_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return start, end, False
    variant = slot.shift_variant
    if variant is not None:
        start = _combine_date_time(slot.slot_date, variant.starts_at)
        end = _combine_date_time(slot.slot_date, variant.ends_at, variant.end_day_offset)
        return start, end, False
    return None, None, True


def slot_to_calendar_event(
    slot: RosterSlot,
    *,
    organization_id: int,
    organization_name: str | None = None,
    shift_group_name: str | None = None,
) -> ShiftCalendarEvent:
    starts_at, ends_at, all_day = _resolve_event_times(slot)
    template = slot.shift_template
    return ShiftCalendarEvent(
        roster_slot_id=slot.id,
        slot_date=slot.slot_date,
        starts_at=starts_at,
        ends_at=ends_at,
        all_day=all_day,
        summary=_summary_for_slot(slot),
        description=_description_lines(
            category=template.category if template else None,
            day_class=slot.day_class,
            shift_group_name=shift_group_name,
            organization_name=organization_name,
        ),
        uid=event_uid(organization_id=organization_id, roster_slot_id=slot.id),
    )


def build_ics_calendar(events: list[ShiftCalendarEvent], *, calendar_name: str) -> bytes:
    cal = Calendar()
    cal.add("prodid", "-//Shift Planner//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", calendar_name)
    for item in events:
        vevent = Event()
        vevent.add("uid", item.uid)
        vevent.add("summary", item.summary)
        if item.description:
            vevent.add("description", item.description)
        if item.all_day or item.starts_at is None or item.ends_at is None:
            vevent.add("dtstart", item.slot_date)
            vevent.add("dtend", item.slot_date + timedelta(days=1))
        else:
            vevent.add("dtstart", item.starts_at)
            vevent.add("dtend", item.ends_at)
        cal.add_component(vevent)
    return cal.to_ical()


def _slot_visible_for_member(
    db: Session,
    *,
    slot: RosterSlot,
    organization_id: int,
    shift_group_ids: set[int],
) -> bool:
    period = slot.planning_period
    if period is None or slot.shift_template_id is None:
        return False
    template_group_ids = set(
        db.scalars(
            select(ShiftGroupShiftTemplate.shift_group_id).where(
                ShiftGroupShiftTemplate.shift_template_id == slot.shift_template_id,
                ShiftGroupShiftTemplate.shift_group_id.in_(shift_group_ids),
            )
        ).all()
    )
    if not template_group_ids:
        return False
    for group_id in template_group_ids:
        row = get_shift_group_planning_status(
            db,
            planning_period_id=period.id,
            shift_group_id=group_id,
            organization_id=organization_id,
        )
        if row is not None and is_team_member_roster_visible(row.status):
            return True
    return False


def _load_org_and_group_names(
    db: Session,
    *,
    organization_id: int,
    shift_group_id: int | None,
) -> tuple[str | None, str | None]:
    org_name = db.scalar(select(Organization.name).where(Organization.id == organization_id))
    group_name = None
    if shift_group_id is not None:
        group = db.get(ShiftGroup, shift_group_id)
        group_name = group.name if group else None
    return org_name, group_name


def list_member_calendar_events(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    shift_group_id: int,
    planning_period_id: int | None = None,
    roster_slot_id: int | None = None,
) -> list[ShiftCalendarEvent]:
    require_shift_group(db, shift_group_id, organization_id)
    template_ids, _ = _scope_template_and_member_ids(
        db,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        shift_group_ids=None,
    )
    if not template_ids:
        return []
    org_name, group_name = _load_org_and_group_names(
        db, organization_id=organization_id, shift_group_id=shift_group_id
    )
    stmt = (
        select(RosterSlot)
        .options(
            joinedload(RosterSlot.shift_template),
            joinedload(RosterSlot.shift_variant),
            joinedload(RosterSlot.planning_period),
        )
        .join(RosterSlotAssignment, RosterSlotAssignment.roster_slot_id == RosterSlot.id)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            RosterSlotAssignment.team_member_id == team_member_id,
            RosterSlot.shift_template_id.in_(template_ids),
        )
        .order_by(RosterSlot.slot_date, RosterSlot.starts_at)
    )
    if planning_period_id is not None:
        stmt = stmt.where(RosterSlot.planning_period_id == planning_period_id)
    if roster_slot_id is not None:
        stmt = stmt.where(RosterSlot.id == roster_slot_id)
    events: list[ShiftCalendarEvent] = []
    shift_group_ids = {shift_group_id}
    for slot in db.scalars(stmt).unique():
        if not _slot_visible_for_member(
            db,
            slot=slot,
            organization_id=organization_id,
            shift_group_ids=shift_group_ids,
        ):
            continue
        events.append(
            slot_to_calendar_event(
                slot,
                organization_id=organization_id,
                organization_name=org_name,
                shift_group_name=group_name,
            )
        )
    return events


def export_member_shifts_ics(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    shift_group_id: int,
    planning_period_id: int | None = None,
    roster_slot_id: int | None = None,
    calendar_name: str,
) -> bytes:
    events = list_member_calendar_events(
        db,
        organization_id=organization_id,
        team_member_id=team_member_id,
        shift_group_id=shift_group_id,
        planning_period_id=planning_period_id,
        roster_slot_id=roster_slot_id,
    )
    if roster_slot_id is not None and not events:
        raise ValueError("Roster slot not found or not visible")
    return build_ics_calendar(events, calendar_name=calendar_name)


def export_single_roster_slot_ics(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    roster_slot_id: int,
    calendar_name: str,
) -> bytes:
    slot = assert_member_assigned_to_slot(
        db,
        organization_id=organization_id,
        team_member_id=team_member_id,
        roster_slot_id=roster_slot_id,
    )
    if slot.shift_template_id is None:
        raise ValueError("Roster slot not found or not visible")
    member_groups = team_member_shift_group_ids(db, team_member_id)
    template_group_ids = set(
        db.scalars(
            select(ShiftGroupShiftTemplate.shift_group_id).where(
                ShiftGroupShiftTemplate.shift_template_id == slot.shift_template_id,
                ShiftGroupShiftTemplate.shift_group_id.in_(member_groups),
            )
        ).all()
    )
    if not template_group_ids:
        raise ValueError("Roster slot not found or not visible")
    if not _slot_visible_for_member(
        db,
        slot=slot,
        organization_id=organization_id,
        shift_group_ids=template_group_ids,
    ):
        raise ValueError("Roster slot not found or not visible")
    org_name, group_name = _load_org_and_group_names(
        db, organization_id=organization_id, shift_group_id=next(iter(template_group_ids))
    )
    event = slot_to_calendar_event(
        slot,
        organization_id=organization_id,
        organization_name=org_name,
        shift_group_name=group_name,
    )
    return build_ics_calendar([event], calendar_name=calendar_name)


def assert_member_assigned_to_slot(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    roster_slot_id: int,
) -> RosterSlot:
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == roster_slot_id)
    )
    if assignment is None or assignment.team_member_id != team_member_id:
        raise PermissionError("Not assigned to this roster slot")
    slot = db.scalar(
        select(RosterSlot)
        .options(
            joinedload(RosterSlot.shift_template),
            joinedload(RosterSlot.shift_variant),
            joinedload(RosterSlot.planning_period),
        )
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .where(RosterSlot.id == roster_slot_id, PlanningPeriod.organization_id == organization_id)
    )
    if slot is None:
        raise ValueError("Roster slot not found")
    return slot
