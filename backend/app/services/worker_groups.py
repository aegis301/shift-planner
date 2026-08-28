from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmploymentPeriod, WorkerGroup
from app.schemas import (
    WorkerGroupCategoryRule,
    WorkerGroupCreate,
    WorkerGroupRead,
    WorkerGroupStatusMapping,
    WorkerGroupUpdate,
)
from app.services.audit import record_audit

DEFAULT_CATEGORY_RULES: list[dict[str, Any]] = [
    {"category": "bereitschaftsdienst", "counts_toward_contract": False, "credit_mode": "duration"},
    {"category": "rufdienst", "counts_toward_contract": False, "credit_mode": "none"},
    {"category": "spaetdienst", "counts_toward_contract": True, "credit_mode": "duration"},
    {"category": "other", "counts_toward_contract": True, "credit_mode": "duration"},
]

DEFAULT_STATUS_MAPPINGS: list[dict[str, Any]] = [
    {"code": "urlaub", "absence_kind": "vacation", "consumes_vacation": True, "counts_as_work_day": True},
    {"code": "forschung", "absence_kind": "other", "consumes_vacation": False, "counts_as_work_day": True},
    {"code": "lehre", "absence_kind": "other", "consumes_vacation": False, "counts_as_work_day": True},
    {"code": "frei", "absence_kind": "none", "consumes_vacation": False, "counts_as_work_day": False},
]


def _dump_pattern(items: list) -> list[dict[str, Any]]:
    return [
        {
            "weekday": item.weekday,
            "starts_at": item.starts_at.isoformat(timespec="minutes"),
            "ends_at": item.ends_at.isoformat(timespec="minutes"),
        }
        for item in items
    ]


def _dump_category_rules(items: list[WorkerGroupCategoryRule]) -> list[dict[str, Any]]:
    return [item.model_dump() for item in items]


def _dump_status_mappings(items: list[WorkerGroupStatusMapping]) -> list[dict[str, Any]]:
    return [item.model_dump() for item in items]


def worker_group_to_read(row: WorkerGroup) -> WorkerGroupRead:
    return WorkerGroupRead(
        id=row.id,
        name=row.name,
        weekly_hours_at_100=float(row.weekly_hours_at_100),
        vacation_days_at_100=float(row.vacation_days_at_100),
        regular_week_pattern=row.regular_week_pattern or [],
        category_rules=row.category_rules or [],
        status_mappings=row.status_mappings or [],
        display_order=row.display_order,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_worker_groups(db: Session, *, organization_id: int, active_only: bool = False) -> list[WorkerGroup]:
    stmt = select(WorkerGroup).where(WorkerGroup.organization_id == organization_id)
    if active_only:
        stmt = stmt.where(WorkerGroup.is_active.is_(True))
    stmt = stmt.order_by(WorkerGroup.display_order, func.lower(WorkerGroup.name))
    return list(db.scalars(stmt))


def get_worker_group_or_none(db: Session, worker_group_id: int, *, organization_id: int) -> WorkerGroup | None:
    row = db.get(WorkerGroup, worker_group_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def create_worker_group(
    db: Session,
    payload: WorkerGroupCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> WorkerGroup:
    name = payload.name.strip()
    existing = db.scalar(
        select(WorkerGroup).where(WorkerGroup.organization_id == organization_id, WorkerGroup.name == name)
    )
    if existing is not None:
        raise ValueError("A worker group with this name already exists")
    category_rules = _dump_category_rules(payload.category_rules) if payload.category_rules else list(DEFAULT_CATEGORY_RULES)
    status_mappings = (
        _dump_status_mappings(payload.status_mappings) if payload.status_mappings else list(DEFAULT_STATUS_MAPPINGS)
    )
    row = WorkerGroup(
        organization_id=organization_id,
        name=name,
        weekly_hours_at_100=payload.weekly_hours_at_100,
        vacation_days_at_100=payload.vacation_days_at_100,
        regular_week_pattern=_dump_pattern(payload.regular_week_pattern),
        category_rules=category_rules,
        status_mappings=status_mappings,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    record_audit(db, actor=actor, source=source, action="create", entity_type="worker_group", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def update_worker_group(
    db: Session,
    worker_group_id: int,
    payload: WorkerGroupUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> WorkerGroup | None:
    row = get_worker_group_or_none(db, worker_group_id, organization_id=organization_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = data["name"].strip()
        other = db.scalar(
            select(WorkerGroup).where(
                WorkerGroup.organization_id == organization_id,
                WorkerGroup.name == name,
                WorkerGroup.id != row.id,
            )
        )
        if other is not None:
            raise ValueError("A worker group with this name already exists")
        row.name = name
        data.pop("name")
    if "regular_week_pattern" in data and payload.regular_week_pattern is not None:
        row.regular_week_pattern = _dump_pattern(payload.regular_week_pattern)
        data.pop("regular_week_pattern")
    if "category_rules" in data and payload.category_rules is not None:
        row.category_rules = _dump_category_rules(payload.category_rules)
        data.pop("category_rules")
    if "status_mappings" in data and payload.status_mappings is not None:
        row.status_mappings = _dump_status_mappings(payload.status_mappings)
        data.pop("status_mappings")
    for key, value in data.items():
        setattr(row, key, value)
    record_audit(db, actor=actor, source=source, action="update", entity_type="worker_group", entity_id=row.id)
    db.commit()
    db.refresh(row)
    return row


def delete_worker_group(
    db: Session, worker_group_id: int, *, organization_id: int, actor: str, source: str
) -> bool:
    row = get_worker_group_or_none(db, worker_group_id, organization_id=organization_id)
    if row is None:
        return False
    in_use = db.scalar(
        select(func.count()).select_from(EmploymentPeriod).where(EmploymentPeriod.worker_group_id == row.id)
    )
    if in_use:
        raise ValueError("Worker group is assigned to team members")
    record_audit(db, actor=actor, source=source, action="delete", entity_type="worker_group", entity_id=row.id)
    db.delete(row)
    db.commit()
    return True
