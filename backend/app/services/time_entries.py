from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TeamMember, TimeAccountOpening, TimeEntry
from app.schemas import (
    TimeAccountOpeningRead,
    TimeAccountOpeningUpsert,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryUpdate,
)
from app.services.audit import record_audit
from app.services.employment_periods import employment_on_date, list_employment_periods
from app.services.worker_groups import get_worker_group_or_none

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def minutes_from_interval(started_at: datetime, ended_at: datetime) -> int:
    if ended_at <= started_at:
        raise ValueError("ended_at must be after started_at")
    return int((ended_at - started_at).total_seconds() // 60)


def parse_pattern_time(raw: str) -> time:
    parts = raw.strip().split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=hour, minute=minute)


def pattern_minutes(starts_at: str, ends_at: str) -> int:
    start = datetime.combine(date.min, parse_pattern_time(starts_at))
    end = datetime.combine(date.min, parse_pattern_time(ends_at))
    if end <= start:
        end += timedelta(days=1)
    return int((end - start).total_seconds() // 60)


def category_rule_for(group, category: str | None) -> dict:
    rules = list(group.category_rules or []) if group is not None else []
    for rule in rules:
        if rule.get("category") == category:
            return rule
    return {"category": category, "counts_toward_contract": True, "credit_mode": "duration"}


def status_mapping_for(group, code: str | None) -> dict | None:
    if not code or group is None:
        return None
    for item in group.status_mappings or []:
        if item.get("code") == code:
            return item
    return None


def expected_minutes_for_day(*, group, employment_percentage: int, on_date: date) -> int:
    if group is None:
        return 0
    pct = employment_percentage / 100
    weekday = WEEKDAYS[on_date.weekday()]
    for item in group.regular_week_pattern or []:
        if item.get("weekday") == weekday:
            return round(pattern_minutes(item["starts_at"], item["ends_at"]) * pct)
    if on_date.weekday() >= 5:
        return 0
    weekly_minutes = float(group.weekly_hours_at_100) * 60
    return round(weekly_minutes / 5 * pct)


def time_entry_to_read(row: TimeEntry) -> TimeEntryRead:
    return TimeEntryRead.model_validate(row)


def list_time_entries(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    from_date: date,
    to_date: date,
) -> list[TimeEntry]:
    stmt = (
        select(TimeEntry)
        .where(
            TimeEntry.team_member_id == team_member_id,
            TimeEntry.organization_id == organization_id,
            TimeEntry.entry_date >= from_date,
            TimeEntry.entry_date <= to_date,
        )
        .order_by(TimeEntry.entry_date, TimeEntry.started_at, TimeEntry.id)
    )
    return list(db.scalars(stmt))


def list_time_entries_for_members(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: list[int],
    from_date: date,
    to_date: date,
) -> list[TimeEntry]:
    if not team_member_ids:
        return []
    stmt = select(TimeEntry).where(
        TimeEntry.organization_id == organization_id,
        TimeEntry.team_member_id.in_(team_member_ids),
        TimeEntry.entry_date >= from_date,
        TimeEntry.entry_date <= to_date,
    )
    return list(db.scalars(stmt))


def _require_member(db: Session, team_member_id: int, organization_id: int) -> TeamMember:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    return member


def _resolve_duration_and_times(payload: TimeEntryCreate | TimeEntryUpdate, *, existing: TimeEntry | None = None) -> tuple[bool, datetime | None, datetime | None, int]:
    kind = payload.kind if payload.kind is not None else (existing.kind if existing is not None else "work")
    all_day = payload.all_day if payload.all_day is not None else (existing.all_day if existing is not None else False)
    started_at = payload.started_at if "started_at" in payload.model_fields_set or existing is None else existing.started_at
    ended_at = payload.ended_at if "ended_at" in payload.model_fields_set or existing is None else existing.ended_at
    if isinstance(payload, TimeEntryCreate):
        started_at = payload.started_at
        ended_at = payload.ended_at
        all_day = payload.all_day
        kind = payload.kind
    duration = payload.duration_minutes
    if kind == "absence" or all_day:
        return True, None, None, duration or 0
    if started_at is not None and ended_at is not None:
        return False, started_at, ended_at, minutes_from_interval(started_at, ended_at)
    if duration is not None:
        return False, started_at, ended_at, duration
    raise ValueError("Work entries need started_at and ended_at, or duration_minutes")


def _assert_no_work_overlap(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    started_at: datetime,
    ended_at: datetime,
    exclude_id: int | None = None,
) -> None:
    stmt = select(TimeEntry).where(
        TimeEntry.team_member_id == team_member_id,
        TimeEntry.organization_id == organization_id,
        TimeEntry.kind == "work",
        TimeEntry.all_day.is_(False),
        TimeEntry.started_at.is_not(None),
        TimeEntry.ended_at.is_not(None),
    )
    for row in db.scalars(stmt):
        if exclude_id is not None and row.id == exclude_id:
            continue
        if row.started_at is None or row.ended_at is None:
            continue
        if started_at < row.ended_at and row.started_at < ended_at:
            raise ValueError("Time entries overlap")


def create_time_entry(
    db: Session,
    payload: TimeEntryCreate,
    *,
    team_member_id: int,
    organization_id: int,
    actor: str,
    source: str,
) -> TimeEntry:
    _require_member(db, team_member_id, organization_id)
    all_day, started_at, ended_at, duration = _resolve_duration_and_times(payload)
    counts = payload.counts_toward_contract
    if counts is None:
        if payload.kind == "absence":
            counts = False
        else:
            rule = {"counts_toward_contract": True}
            periods = list_employment_periods(db, team_member_id=team_member_id, organization_id=organization_id)
            emp = employment_on_date(periods, payload.entry_date)
            if emp is not None:
                group = get_worker_group_or_none(db, emp.worker_group_id, organization_id=organization_id)
                rule = category_rule_for(group, payload.shift_template_category)
                if rule.get("credit_mode") == "none":
                    duration = 0
            counts = bool(rule.get("counts_toward_contract", True))
    if not all_day and started_at is not None and ended_at is not None:
        _assert_no_work_overlap(
            db,
            team_member_id=team_member_id,
            organization_id=organization_id,
            started_at=started_at,
            ended_at=ended_at,
        )
    row = TimeEntry(
        organization_id=organization_id,
        team_member_id=team_member_id,
        entry_date=payload.entry_date,
        kind=payload.kind,
        source=payload.source,
        all_day=all_day,
        started_at=started_at,
        ended_at=ended_at,
        duration_minutes=duration,
        counts_toward_contract=counts,
        shift_template_category=payload.shift_template_category,
        planning_day_status_code=payload.planning_day_status_code,
        roster_slot_id=payload.roster_slot_id,
        comment=payload.comment,
    )
    db.add(row)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="time_entry", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def update_time_entry(
    db: Session,
    entry_id: int,
    payload: TimeEntryUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> TimeEntry | None:
    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != organization_id:
        return None
    if row.source != "manual" and payload.kind is None:
        row.source = "manual"
    merged = TimeEntryCreate(
        entry_date=payload.entry_date or row.entry_date,
        kind=payload.kind or row.kind,  # type: ignore[arg-type]
        source="manual",
        all_day=payload.all_day if payload.all_day is not None else row.all_day,
        started_at=payload.started_at if "started_at" in payload.model_fields_set else row.started_at,
        ended_at=payload.ended_at if "ended_at" in payload.model_fields_set else row.ended_at,
        duration_minutes=payload.duration_minutes if payload.duration_minutes is not None else row.duration_minutes,
        counts_toward_contract=payload.counts_toward_contract
        if payload.counts_toward_contract is not None
        else row.counts_toward_contract,
        shift_template_category=payload.shift_template_category
        if payload.shift_template_category is not None
        else row.shift_template_category,  # type: ignore[arg-type]
        planning_day_status_code=payload.planning_day_status_code
        if payload.planning_day_status_code is not None
        else row.planning_day_status_code,
        comment=payload.comment if payload.comment is not None else row.comment,
    )
    all_day, started_at, ended_at, duration = _resolve_duration_and_times(merged, existing=row)
    if not all_day and started_at is not None and ended_at is not None:
        _assert_no_work_overlap(
            db,
            team_member_id=row.team_member_id,
            organization_id=organization_id,
            started_at=started_at,
            ended_at=ended_at,
            exclude_id=row.id,
        )
    row.entry_date = merged.entry_date
    row.kind = merged.kind
    row.source = "manual"
    row.all_day = all_day
    row.started_at = started_at
    row.ended_at = ended_at
    row.duration_minutes = duration
    row.counts_toward_contract = merged.counts_toward_contract if merged.counts_toward_contract is not None else row.counts_toward_contract
    if payload.shift_template_category is not None:
        row.shift_template_category = payload.shift_template_category
    if payload.planning_day_status_code is not None:
        row.planning_day_status_code = payload.planning_day_status_code
    if payload.comment is not None:
        row.comment = payload.comment
    record_audit(db, actor=actor, source=source, action="update", entity_type="time_entry", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def delete_time_entry(db: Session, entry_id: int, *, organization_id: int, actor: str, source: str) -> bool:
    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != organization_id:
        return False
    record_audit(db, actor=actor, source=source, action="delete", entity_type="time_entry", entity_id=row.id)
    db.delete(row)
    db.commit()
    return True


def opening_to_read(row: TimeAccountOpening) -> TimeAccountOpeningRead:
    return TimeAccountOpeningRead(
        id=row.id,
        team_member_id=row.team_member_id,
        as_of_date=row.as_of_date,
        overtime_minutes=row.overtime_minutes,
        vacation_days_remaining=float(row.vacation_days_remaining),
        sick_days_used_ytd=float(row.sick_days_used_ytd),
    )


def get_opening_balance(
    db: Session, *, team_member_id: int, organization_id: int
) -> TimeAccountOpening | None:
    return db.scalar(
        select(TimeAccountOpening).where(
            TimeAccountOpening.team_member_id == team_member_id,
            TimeAccountOpening.organization_id == organization_id,
        )
    )


def list_opening_balances(db: Session, *, organization_id: int) -> list[TimeAccountOpening]:
    stmt = select(TimeAccountOpening).where(TimeAccountOpening.organization_id == organization_id)
    return list(db.scalars(stmt))


def upsert_opening_balance(
    db: Session,
    payload: TimeAccountOpeningUpsert,
    *,
    team_member_id: int,
    organization_id: int,
    actor: str,
    source: str,
) -> TimeAccountOpening:
    _require_member(db, team_member_id, organization_id)
    row = get_opening_balance(db, team_member_id=team_member_id, organization_id=organization_id)
    if row is None:
        row = TimeAccountOpening(
            organization_id=organization_id,
            team_member_id=team_member_id,
            as_of_date=payload.as_of_date,
            overtime_minutes=payload.overtime_minutes,
            vacation_days_remaining=payload.vacation_days_remaining,
            sick_days_used_ytd=payload.sick_days_used_ytd,
        )
        db.add(row)
        action = "create"
    else:
        row.as_of_date = payload.as_of_date
        row.overtime_minutes = payload.overtime_minutes
        row.vacation_days_remaining = payload.vacation_days_remaining
        row.sick_days_used_ytd = payload.sick_days_used_ytd
        action = "update"
    db.flush()
    record_audit(db, actor=actor, source=source, action=action, entity_type="time_account_opening", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row
