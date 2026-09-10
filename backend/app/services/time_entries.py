from datetime import date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    ContractGroup,
    EmploymentPeriod,
    PlanningCell,
    PlanningPeriod,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
    TimeEntry,
)
from app.schemas import (
    ContractCategoryRule,
    ContractStatusMapping,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryReconciliationItem,
    TimeEntryUpdate,
)
from app.services.audit import record_audit
from app.services.contract_groups import list_contract_groups
from app.services.shift_groups import _stint_active_on

SOURCE_ROSTER = "roster"
SOURCE_DAY_STATUS = "day_status"
SOURCE_MANUAL = "manual"

KIND_WORK = "work"
KIND_ABSENCE = "absence"

_APPLY_FIELDS = (
    "kind",
    "all_day",
    "started_at",
    "ended_at",
    "duration_minutes",
    "counts_toward_contract",
    "consumes_vacation",
    "shift_template_category",
    "planning_day_status_code",
    "comment",
)


def time_entry_to_read(row: TimeEntry) -> TimeEntryRead:
    return TimeEntryRead.model_validate(row)


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _snapshot(desired: dict[str, Any]) -> dict[str, Any]:
    return {key: _jsonable(value) for key, value in desired.items()}


def _match_key(row: TimeEntry) -> tuple:
    return (row.source, row.team_member_id, row.entry_date, row.roster_slot_id, row.shift_group_id)


def _desired_key(desired: dict[str, Any]) -> tuple:
    return (
        desired["source"],
        desired["team_member_id"],
        desired["entry_date"],
        desired.get("roster_slot_id"),
        desired.get("shift_group_id"),
    )


def _duration_minutes(started_at: datetime | None, ended_at: datetime | None) -> int:
    if started_at is None or ended_at is None:
        return 0
    delta = ended_at - started_at
    return max(0, int(delta.total_seconds() // 60))


def _contract_group_on(member: TeamMember, on_date: date, groups_by_id: dict[int, ContractGroup]) -> ContractGroup | None:
    for period in member.employment_periods:
        if _stint_active_on(period, on_date):
            return groups_by_id.get(period.contract_group_id)
    return None


def _category_counts_toward(group: ContractGroup | None, category: str | None) -> bool:
    if group is None or not category:
        return True
    for raw in group.category_rules or []:
        rule = ContractCategoryRule.model_validate(raw)
        if rule.category == category:
            return rule.counts_toward_contract
    return True


def _status_mapping(group: ContractGroup | None, code: str) -> ContractStatusMapping | None:
    if group is None:
        return None
    for raw in group.status_mappings or []:
        mapping = ContractStatusMapping.model_validate(raw)
        if mapping.code == code:
            return mapping
    return None


def _desired_from_assignment(
    assignment: RosterSlotAssignment,
    slot: RosterSlot,
    organization_id: int,
    group: ContractGroup | None,
) -> dict[str, Any]:
    category = slot.shift_template.category if slot.shift_template is not None else None
    started_at = slot.starts_at
    ended_at = slot.ends_at
    return {
        "organization_id": organization_id,
        "team_member_id": assignment.team_member_id,
        "entry_date": slot.slot_date,
        "kind": KIND_WORK,
        "source": SOURCE_ROSTER,
        "all_day": False,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_minutes": _duration_minutes(started_at, ended_at),
        "counts_toward_contract": _category_counts_toward(group, category),
        "consumes_vacation": False,
        "shift_template_category": category,
        "planning_day_status_code": None,
        "roster_slot_id": slot.id,
        "shift_group_id": None,
        "comment": assignment.comment,
    }


def _desired_from_cell(
    cell: PlanningCell,
    organization_id: int,
    group: ContractGroup | None,
) -> dict[str, Any] | None:
    mapping = _status_mapping(group, cell.status)
    if mapping is None or mapping.absence_kind == "none":
        return None
    return {
        "organization_id": organization_id,
        "team_member_id": cell.team_member_id,
        "entry_date": cell.cell_date,
        "kind": KIND_ABSENCE,
        "source": SOURCE_DAY_STATUS,
        "all_day": True,
        "started_at": None,
        "ended_at": None,
        "duration_minutes": 0,
        "counts_toward_contract": mapping.counts_as_work_day,
        "consumes_vacation": mapping.consumes_vacation,
        "shift_template_category": None,
        "planning_day_status_code": cell.status,
        "roster_slot_id": None,
        "shift_group_id": cell.shift_group_id,
        "comment": cell.comment,
    }


def _apply_derived(row: TimeEntry, desired: dict[str, Any]) -> None:
    corrected = set(row.corrected_fields or [])
    row.derived_snapshot = _snapshot(desired)
    row.source = desired["source"]
    row.team_member_id = desired["team_member_id"]
    row.entry_date = desired["entry_date"]
    row.organization_id = desired["organization_id"]
    row.roster_slot_id = desired.get("roster_slot_id")
    row.shift_group_id = desired.get("shift_group_id")
    for field in _APPLY_FIELDS:
        if field in corrected:
            continue
        setattr(row, field, desired[field])


def get_time_entry(db: Session, entry_id: int, *, organization_id: int) -> TimeEntry | None:
    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def list_time_entries(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[TimeEntry]:
    stmt = select(TimeEntry).where(
        TimeEntry.organization_id == organization_id,
        TimeEntry.team_member_id == team_member_id,
    )
    if start_date is not None:
        stmt = stmt.where(TimeEntry.entry_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(TimeEntry.entry_date <= end_date)
    return list(db.scalars(stmt.order_by(TimeEntry.entry_date, TimeEntry.id)))


def derive_entries(
    db: Session,
    *,
    organization_id: int,
    start_date: date,
    end_date: date,
    member_ids: list[int] | None = None,
) -> list[TimeEntry]:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    member_stmt = select(TeamMember).options(joinedload(TeamMember.employment_periods)).where(
        TeamMember.organization_id == organization_id
    )
    if member_ids is not None:
        if not member_ids:
            return []
        member_stmt = member_stmt.where(TeamMember.id.in_(member_ids))
    members = list(db.scalars(member_stmt).unique())
    member_id_set = {member.id for member in members}
    if not member_id_set:
        return []
    groups = {row.id: row for row in list_contract_groups(db, organization_id=organization_id)}
    member_by_id = {member.id: member for member in members}

    assignment_stmt = (
        select(RosterSlotAssignment)
        .join(RosterSlot, RosterSlot.id == RosterSlotAssignment.roster_slot_id)
        .join(PlanningPeriod, PlanningPeriod.id == RosterSlot.planning_period_id)
        .options(
            joinedload(RosterSlotAssignment.roster_slot).joinedload(RosterSlot.shift_template),
        )
        .where(
            PlanningPeriod.organization_id == organization_id,
            RosterSlot.slot_date >= start_date,
            RosterSlot.slot_date <= end_date,
            RosterSlotAssignment.team_member_id.in_(member_id_set),
        )
    )
    assignments = list(db.scalars(assignment_stmt).unique())

    cell_stmt = (
        select(PlanningCell)
        .join(PlanningPeriod, PlanningPeriod.id == PlanningCell.planning_period_id)
        .where(
            PlanningPeriod.organization_id == organization_id,
            PlanningCell.cell_date >= start_date,
            PlanningCell.cell_date <= end_date,
            PlanningCell.team_member_id.in_(member_id_set),
        )
    )
    cells = list(db.scalars(cell_stmt))

    desired_rows: list[dict[str, Any]] = []
    for assignment in assignments:
        slot = assignment.roster_slot
        member = member_by_id.get(assignment.team_member_id)
        group = _contract_group_on(member, slot.slot_date, groups) if member is not None else None
        desired_rows.append(_desired_from_assignment(assignment, slot, organization_id, group))
    for cell in cells:
        member = member_by_id.get(cell.team_member_id)
        group = _contract_group_on(member, cell.cell_date, groups) if member is not None else None
        desired = _desired_from_cell(cell, organization_id, group)
        if desired is not None:
            desired_rows.append(desired)

    existing = list(
        db.scalars(
            select(TimeEntry).where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.entry_date >= start_date,
                TimeEntry.entry_date <= end_date,
                TimeEntry.source.in_((SOURCE_ROSTER, SOURCE_DAY_STATUS)),
                TimeEntry.team_member_id.in_(member_id_set),
            )
        )
    )
    existing_by_key = {_match_key(row): row for row in existing}
    desired_keys = {_desired_key(row) for row in desired_rows}

    for desired in desired_rows:
        key = _desired_key(desired)
        row = existing_by_key.get(key)
        if row is None:
            row = TimeEntry(
                organization_id=organization_id,
                team_member_id=desired["team_member_id"],
                entry_date=desired["entry_date"],
                kind=desired["kind"],
                source=desired["source"],
                corrected_fields=[],
            )
            db.add(row)
        _apply_derived(row, desired)

    for row in existing:
        if _match_key(row) not in desired_keys:
            db.delete(row)

    db.commit()
    return []


def refresh_derived_window(
    db: Session,
    *,
    organization_id: int,
    member_ids: list[int],
    start_date: date,
    end_date: date,
) -> None:
    if not member_ids:
        return
    derive_entries(
        db,
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
        member_ids=member_ids,
    )


def list_reconciliation(
    db: Session,
    *,
    organization_id: int,
    team_member_id: int,
    start_date: date,
    end_date: date,
) -> list[TimeEntryReconciliationItem]:
    rows = list_time_entries(
        db,
        organization_id=organization_id,
        team_member_id=team_member_id,
        start_date=start_date,
        end_date=end_date,
    )
    items: list[TimeEntryReconciliationItem] = []
    for row in rows:
        effective = time_entry_to_read(row)
        derived = row.derived_snapshot
        diverges = False
        if derived:
            for field in _APPLY_FIELDS:
                if _jsonable(getattr(row, field)) != derived.get(field):
                    diverges = True
                    break
        items.append(
            TimeEntryReconciliationItem(
                id=row.id,
                team_member_id=row.team_member_id,
                entry_date=row.entry_date,
                source=row.source,  # type: ignore[arg-type]
                derived=derived,
                effective=effective,
                corrected_fields=list(row.corrected_fields or []),
                diverges=diverges,
            )
        )
    return items


def create_manual_entry(
    db: Session,
    payload: TimeEntryCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> TimeEntry:
    member = db.get(TeamMember, payload.team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    row = TimeEntry(
        organization_id=organization_id,
        team_member_id=payload.team_member_id,
        entry_date=payload.entry_date,
        kind=payload.kind,
        source=SOURCE_MANUAL,
        all_day=payload.all_day,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_minutes=payload.duration_minutes,
        counts_toward_contract=payload.counts_toward_contract,
        consumes_vacation=payload.consumes_vacation,
        shift_template_category=payload.shift_template_category,
        planning_day_status_code=payload.planning_day_status_code,
        roster_slot_id=None,
        shift_group_id=None,
        comment=payload.comment,
        derived_snapshot=None,
        corrected_fields=[],
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
    changes = payload.model_dump(exclude_unset=True)
    corrected = list(row.corrected_fields or [])
    for field, value in changes.items():
        setattr(row, field, value)
        if row.source != SOURCE_MANUAL and field not in corrected:
            corrected.append(field)
    row.corrected_fields = corrected
    record_audit(db, actor=actor, source=source, action="update", entity_type="time_entry", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def delete_time_entry(
    db: Session,
    entry_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> bool:
    row = db.get(TimeEntry, entry_id)
    if row is None or row.organization_id != organization_id:
        return False
    if row.source != SOURCE_MANUAL:
        raise ValueError("Only manual time entries can be deleted")
    record_audit(db, actor=actor, source=source, action="delete", entity_type="time_entry", entity_id=row.id)
    db.delete(row)
    db.commit()
    return True


def load_time_entries_for_window(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: set[int],
    start_date: date,
    end_date: date,
) -> dict[int, tuple[TimeEntry, ...]]:
    if not team_member_ids:
        return {}
    rows = list(
        db.scalars(
            select(TimeEntry).where(
                TimeEntry.organization_id == organization_id,
                TimeEntry.team_member_id.in_(team_member_ids),
                TimeEntry.entry_date >= start_date,
                TimeEntry.entry_date <= end_date,
            )
        )
    )
    grouped: dict[int, list[TimeEntry]] = {}
    for row in rows:
        grouped.setdefault(row.team_member_id, []).append(row)
    return {member_id: tuple(items) for member_id, items in grouped.items()}


def load_employment_periods_for_members(
    db: Session,
    *,
    team_member_ids: set[int],
    start_date: date,
    end_date: date,
) -> dict[int, tuple[EmploymentPeriod, ...]]:
    if not team_member_ids:
        return {}
    rows = list(
        db.scalars(
            select(EmploymentPeriod).where(
                EmploymentPeriod.team_member_id.in_(team_member_ids),
                EmploymentPeriod.start_date <= end_date,
                or_(EmploymentPeriod.end_date.is_(None), EmploymentPeriod.end_date >= start_date),
            )
        )
    )
    grouped: dict[int, list[EmploymentPeriod]] = {}
    for row in rows:
        grouped.setdefault(row.team_member_id, []).append(row)
    return {member_id: tuple(items) for member_id, items in grouped.items()}
