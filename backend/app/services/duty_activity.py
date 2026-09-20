from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ContractGroup,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
    TimeEntry,
)
from app.schemas import DutyActivityCreate, DutyActivityReason, DutyActivityUpdate, TimeEntryRead
from app.services.audit import record_audit
from app.services.contract_groups import list_contract_groups
from app.services.holidays import classify_day
from app.services.shift_groups import _stint_active_on
from app.services.time_entries import time_entry_to_read
from app.services.work_time_valuation import (
    RUFDIENST,
    resolve_valuation_rule,
    statutory_work_minutes,
    tariff_credit_minutes,
)

KIND_CALL_OUT = "call_out"
KIND_IN_DUTY_ACTIVITY = "in_duty_activity"
SOURCE_DUTY_ACTIVITY = "duty_activity"
DUTY_ACTIVITY_KINDS = frozenset({KIND_CALL_OUT, KIND_IN_DUTY_ACTIVITY})


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def interval_minutes(started_at: datetime | None, ended_at: datetime | None) -> int:
    start = _as_utc(started_at)
    end = _as_utc(ended_at)
    if start is None or end is None or end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


def slot_span(slot: RosterSlot) -> tuple[datetime, datetime]:
    start = _as_utc(slot.starts_at)
    end = _as_utc(slot.ends_at)
    if start is None or end is None:
        raise ValueError("Roster slot has no start and end time")
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def _intervals_overlap(
    left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime
) -> bool:
    return left_start < right_end and right_start < left_end


def _reason_payload(reason: DutyActivityReason | None) -> dict[str, Any] | None:
    if reason is None:
        return None
    return reason.model_dump(exclude_none=True)


def _contract_group_on(
    member: TeamMember, on_date, groups_by_id: dict[int, ContractGroup]
) -> ContractGroup | None:
    for period in member.employment_periods:
        if _stint_active_on(period, on_date):
            return groups_by_id.get(period.contract_group_id)
    return None


def _require_slot(db: Session, roster_slot_id: int, *, organization_id: int) -> RosterSlot:
    slot = db.scalar(
        select(RosterSlot)
        .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.planning_period))
        .where(RosterSlot.id == roster_slot_id)
    )
    if slot is None:
        raise ValueError("Roster slot not found")
    period = slot.planning_period or db.get(PlanningPeriod, slot.planning_period_id)
    if period is None or period.organization_id != organization_id:
        raise ValueError("Roster slot not found")
    return slot


def _require_assignee(db: Session, slot: RosterSlot, team_member_id: int) -> RosterSlotAssignment:
    assignment = db.scalar(
        select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot.id)
    )
    if assignment is None or assignment.team_member_id != team_member_id:
        raise ValueError("Team member is not assigned to this slot")
    return assignment


def _require_member(db: Session, team_member_id: int, *, organization_id: int) -> TeamMember:
    member = db.scalar(
        select(TeamMember)
        .options(joinedload(TeamMember.employment_periods))
        .where(TeamMember.id == team_member_id, TeamMember.organization_id == organization_id)
    )
    if member is None:
        raise ValueError("Team member not found")
    return member


def list_duty_activity_episodes(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    roster_slot_id: int | None = None,
) -> list[TimeEntry]:
    stmt = select(TimeEntry).where(
        TimeEntry.organization_id == organization_id,
        TimeEntry.team_member_id == team_member_id,
        TimeEntry.kind.in_(DUTY_ACTIVITY_KINDS),
    )
    if roster_slot_id is not None:
        stmt = stmt.where(TimeEntry.roster_slot_id == roster_slot_id)
    return list(db.scalars(stmt.order_by(TimeEntry.started_at, TimeEntry.id)))


def list_duty_activity_for_slots(
    db: Session,
    *,
    organization_id: int,
    roster_slot_ids: set[int],
) -> dict[int, list[TimeEntry]]:
    if not roster_slot_ids:
        return {}
    rows = list(
        db.scalars(
            select(TimeEntry).where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.kind.in_(DUTY_ACTIVITY_KINDS),
                TimeEntry.roster_slot_id.in_(roster_slot_ids),
            )
        )
    )
    grouped: dict[int, list[TimeEntry]] = {}
    for row in rows:
        if row.roster_slot_id is None:
            continue
        grouped.setdefault(row.roster_slot_id, []).append(row)
    return grouped


def _assert_episode_fits_slot(
    slot: RosterSlot, started_at: datetime, ended_at: datetime | None
) -> None:
    start = _as_utc(started_at)
    if start is None:
        raise ValueError("started_at is required")
    span_start, span_end = slot_span(slot)
    if start < span_start or start > span_end:
        raise ValueError("Episode must fall inside the slot span")
    end = _as_utc(ended_at)
    if end is None:
        return
    if end <= start:
        raise ValueError("ended_at must be after started_at")
    if end > span_end:
        raise ValueError("Episode must fall inside the slot span")


def _effective_end(slot: RosterSlot, started_at: datetime, ended_at: datetime | None) -> datetime:
    end = _as_utc(ended_at)
    if end is not None:
        return end
    _span_start, span_end = slot_span(slot)
    start = _as_utc(started_at)
    if start is None:
        return span_end
    return max(span_end, start)


def _assert_no_overlap(
    db: Session,
    *,
    organization_id: int,
    slot: RosterSlot,
    started_at: datetime,
    ended_at: datetime | None,
    exclude_id: int | None = None,
) -> None:
    start = _as_utc(started_at)
    if start is None:
        raise ValueError("started_at is required")
    end = _effective_end(slot, start, ended_at)
    rows = list(
        db.scalars(
            select(TimeEntry).where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.kind.in_(DUTY_ACTIVITY_KINDS),
                TimeEntry.roster_slot_id == slot.id,
            )
        )
    )
    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        other_start = _as_utc(row.started_at)
        if other_start is None:
            continue
        other_end = _effective_end(slot, other_start, _as_utc(row.ended_at))
        if _intervals_overlap(start, end, other_start, other_end):
            raise ValueError("Overlapping episodes on the same slot are not allowed")


def find_open_duty_activity(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    roster_slot_id: int,
) -> TimeEntry | None:
    return db.scalar(
        select(TimeEntry)
        .where(
            TimeEntry.organization_id == organization_id,
            TimeEntry.team_member_id == team_member_id,
            TimeEntry.roster_slot_id == roster_slot_id,
            TimeEntry.kind.in_(DUTY_ACTIVITY_KINDS),
            TimeEntry.ended_at.is_(None),
        )
        .order_by(TimeEntry.id)
        .limit(1)
    )

def _episode_minutes_values(
    *,
    slot: RosterSlot,
    group: ContractGroup | None,
    kind: str,
    started_at: datetime,
    ended_at: datetime,
    duration: int,
) -> tuple[int, int, bool]:
    template = slot.shift_template
    if kind == KIND_IN_DUTY_ACTIVITY:
        return 0, 0, False
    rule = resolve_valuation_rule(contract_group=group, template=template)
    episode = SimpleNamespace(
        kind=kind,
        duration_minutes=duration,
        started_at=started_at,
        ended_at=ended_at,
    )
    category = getattr(template, "category", None) if template is not None else None
    if category == RUFDIENST:
        day_class = slot.day_class or classify_day(slot.slot_date)
        statutory = statutory_work_minutes(
            slot=slot,
            contract_group=group,
            template=template,
            day_class=day_class,
            episodes=(episode,),
        )
        credited = tariff_credit_minutes(
            slot=slot,
            contract_group=group,
            template=template,
            day_class=day_class,
            episodes=(episode,),
        )
        return statutory, credited, rule.call_outs_count_as_work
    extra = duration if rule.call_outs_count_as_work else 0
    return extra, extra, rule.call_outs_count_as_work


def record_duty_activity(
    db: Session,
    payload: DutyActivityCreate,
    *,
    organization_id: int,
    team_member_id: int,
    actor: str,
    source: str,
) -> TimeEntry:
    if payload.kind not in DUTY_ACTIVITY_KINDS:
        raise ValueError("kind must be call_out or in_duty_activity")
    member = _require_member(db, team_member_id, organization_id=organization_id)
    slot = _require_slot(db, payload.roster_slot_id, organization_id=organization_id)
    _require_assignee(db, slot, team_member_id)
    started_at = _as_utc(payload.started_at)
    ended_at = _as_utc(payload.ended_at)
    if started_at is None:
        raise ValueError("started_at is required")
    if ended_at is None:
        existing = find_open_duty_activity(
            db,
            organization_id=organization_id,
            team_member_id=team_member_id,
            roster_slot_id=slot.id,
        )
        if existing is not None:
            return existing
    _assert_episode_fits_slot(slot, started_at, ended_at)
    _assert_no_overlap(
        db,
        organization_id=organization_id,
        slot=slot,
        started_at=started_at,
        ended_at=ended_at,
    )
    duration = interval_minutes(started_at, ended_at)
    groups = {row.id: row for row in list_contract_groups(db, organization_id=organization_id)}
    group = _contract_group_on(member, slot.slot_date, groups)
    statutory, credited, counts = _episode_minutes_values(
        slot=slot,
        group=group,
        kind=payload.kind,
        started_at=started_at,
        ended_at=ended_at,
        duration=duration,
    )
    category = slot.shift_template.category if slot.shift_template is not None else None
    row = TimeEntry(
        organization_id=organization_id,
        team_member_id=team_member_id,
        entry_date=slot.slot_date,
        kind=payload.kind,
        source=SOURCE_DUTY_ACTIVITY,
        all_day=False,
        started_at=started_at,
        ended_at=ended_at,
        duration_minutes=duration,
        statutory_minutes=statutory,
        credited_minutes=credited,
        counts_toward_contract=counts,
        consumes_vacation=False,
        shift_template_category=category,
        planning_day_status_code=None,
        roster_slot_id=slot.id,
        shift_group_id=None,
        comment=payload.reason.note if payload.reason is not None else None,
        reason=_reason_payload(payload.reason),
        derived_snapshot=None,
        corrected_fields=[],
    )
    db.add(row)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="time_entry", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def update_duty_activity(
    db: Session,
    entry_id: int,
    payload: DutyActivityUpdate,
    *,
    organization_id: int,
    team_member_id: int,
    actor: str,
    source: str,
) -> TimeEntry:
    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != organization_id:
        raise LookupError("Duty activity episode not found")
    if row.kind not in DUTY_ACTIVITY_KINDS or row.team_member_id != team_member_id:
        raise PermissionError("Can only update your own duty activity episodes")
    if row.roster_slot_id is None:
        raise ValueError("Duty activity episode is missing a roster slot")
    slot = _require_slot(db, row.roster_slot_id, organization_id=organization_id)
    member = _require_member(db, team_member_id, organization_id=organization_id)
    started_at = _as_utc(row.started_at)
    if started_at is None:
        raise ValueError("started_at is required")
    ended_at = _as_utc(payload.ended_at) if payload.ended_at is not None else _as_utc(row.ended_at)
    if payload.ended_at is not None and row.ended_at is not None:
        ended_at = _as_utc(row.ended_at)
    _assert_episode_fits_slot(slot, started_at, ended_at)
    _assert_no_overlap(
        db,
        organization_id=organization_id,
        slot=slot,
        started_at=started_at,
        ended_at=ended_at,
        exclude_id=row.id,
    )
    duration = interval_minutes(started_at, ended_at)
    groups = {group.id: group for group in list_contract_groups(db, organization_id=organization_id)}
    group = _contract_group_on(member, slot.slot_date, groups)
    statutory, credited, counts = _episode_minutes_values(
        slot=slot,
        group=group,
        kind=row.kind,
        started_at=started_at,
        ended_at=ended_at if ended_at is not None else started_at,
        duration=duration,
    )
    row.ended_at = ended_at
    row.duration_minutes = duration
    row.statutory_minutes = statutory
    row.credited_minutes = credited
    row.counts_toward_contract = counts
    if payload.reason is not None:
        row.reason = _reason_payload(payload.reason)
        row.comment = payload.reason.note
    record_audit(db, actor=actor, source=source, action="update", entity_type="time_entry", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def delete_duty_activity(
    db: Session,
    entry_id: int,
    *,
    organization_id: int,
    team_member_id: int,
    actor: str,
    source: str,
) -> bool:
    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != organization_id:
        return False
    if row.kind not in DUTY_ACTIVITY_KINDS or row.team_member_id != team_member_id:
        raise PermissionError("Can only delete your own duty activity episodes")
    record_audit(db, actor=actor, source=source, action="delete", entity_type="time_entry", entity_id=row.id)
    db.delete(row)
    db.commit()
    return True


def duty_activity_to_read(row: TimeEntry) -> TimeEntryRead:
    return time_entry_to_read(row)
