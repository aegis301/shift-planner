from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PlanningPlanVersion, WorkTimeRuleSet
from app.schemas import (
    WorkTimeRule,
    WorkTimeRuleSetCreate,
    WorkTimeRuleSetRead,
    WorkTimeRuleSetUpdate,
)
from app.services.audit import record_audit

_RULES_ADAPTER = TypeAdapter(list[WorkTimeRule])


def _serialize_rules(rules: list) -> list[dict[str, Any]]:
    parsed = _RULES_ADAPTER.validate_python(rules)
    return _RULES_ADAPTER.dump_python(parsed, mode="json")


def _parse_rules(raw: list | None) -> list[WorkTimeRule]:
    return _RULES_ADAPTER.validate_python(raw or [])


def work_time_rule_set_to_read(row: WorkTimeRuleSet) -> WorkTimeRuleSetRead:
    return WorkTimeRuleSetRead(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        version=row.version,
        is_active=row.is_active,
        rules=_parse_rules(row.rules),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_work_time_rule_sets(db: Session, *, organization_id: int) -> list[WorkTimeRuleSet]:
    return list(
        db.scalars(
            select(WorkTimeRuleSet)
            .where(WorkTimeRuleSet.organization_id == organization_id)
            .order_by(WorkTimeRuleSet.name, WorkTimeRuleSet.version.desc())
        )
    )


def get_work_time_rule_set(
    db: Session, rule_set_id: int, *, organization_id: int
) -> WorkTimeRuleSet | None:
    row = db.get(WorkTimeRuleSet, rule_set_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def get_active_work_time_rule_set(db: Session, *, organization_id: int) -> WorkTimeRuleSet | None:
    return db.scalar(
        select(WorkTimeRuleSet).where(
            WorkTimeRuleSet.organization_id == organization_id,
            WorkTimeRuleSet.is_active.is_(True),
        )
    )


def _rule_set_is_referenced(db: Session, rule_set_id: int) -> bool:
    pinned = db.scalar(
        select(func.count()).select_from(PlanningPlanVersion).where(
            PlanningPlanVersion.work_time_rule_set_version_id == rule_set_id
        )
    )
    return bool(pinned)


def _deactivate_other_sets(db: Session, *, organization_id: int, keep_id: int | None) -> None:
    rows = list(
        db.scalars(
            select(WorkTimeRuleSet).where(
                WorkTimeRuleSet.organization_id == organization_id,
                WorkTimeRuleSet.is_active.is_(True),
            )
        )
    )
    for row in rows:
        if keep_id is not None and row.id == keep_id:
            continue
        row.is_active = False


def _next_version(db: Session, *, organization_id: int, name: str) -> int:
    current = db.scalar(
        select(func.max(WorkTimeRuleSet.version)).where(
            WorkTimeRuleSet.organization_id == organization_id,
            WorkTimeRuleSet.name == name,
        )
    )
    return int(current or 0) + 1


def create_work_time_rule_set(
    db: Session,
    payload: WorkTimeRuleSetCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
    commit: bool = True,
) -> WorkTimeRuleSet:
    existing_active = get_active_work_time_rule_set(db, organization_id=organization_id)
    activate = payload.is_active if payload.is_active is not None else existing_active is None
    if activate:
        _deactivate_other_sets(db, organization_id=organization_id, keep_id=None)
    row = WorkTimeRuleSet(
        organization_id=organization_id,
        name=payload.name.strip(),
        version=_next_version(db, organization_id=organization_id, name=payload.name.strip()),
        is_active=activate,
        rules=_serialize_rules(payload.rules),
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="work_time_rule_set",
        entity_id=row.id,
    )
    if commit:
        db.commit()
        db.refresh(row)
    return row


def update_work_time_rule_set(
    db: Session,
    rule_set_id: int,
    payload: WorkTimeRuleSetUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> WorkTimeRuleSet | None:
    row = get_work_time_rule_set(db, rule_set_id, organization_id=organization_id)
    if row is None:
        return None
    changes = payload.model_dump(exclude_unset=True)
    content_changed = any(key in changes for key in ("name", "rules"))
    referenced = _rule_set_is_referenced(db, row.id)
    if referenced and content_changed:
        next_name = str(changes.get("name", row.name)).strip()
        if "rules" in changes:
            next_rules = _serialize_rules(changes["rules"])
        else:
            next_rules = list(row.rules or [])
        activate = changes.get("is_active", True)
        row.is_active = False
        if activate:
            _deactivate_other_sets(db, organization_id=organization_id, keep_id=None)
        successor = WorkTimeRuleSet(
            organization_id=organization_id,
            name=next_name,
            version=_next_version(db, organization_id=organization_id, name=next_name),
            is_active=activate,
            rules=next_rules,
        )
        db.add(successor)
        db.flush()
        record_audit(
            db,
            actor=actor,
            source=source,
            action="create",
            entity_type="work_time_rule_set",
            entity_id=successor.id,
            details={"supersedes_id": row.id},
        )
        db.commit()
        db.refresh(successor)
        return successor
    if "name" in changes and changes["name"] is not None:
        row.name = changes["name"].strip()
    if "rules" in changes and changes["rules"] is not None:
        row.rules = _serialize_rules(changes["rules"])
    if "is_active" in changes and changes["is_active"] is not None:
        if changes["is_active"]:
            _deactivate_other_sets(db, organization_id=organization_id, keep_id=row.id)
            row.is_active = True
        else:
            row.is_active = False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="work_time_rule_set",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


def delete_work_time_rule_set(
    db: Session,
    rule_set_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> bool:
    row = get_work_time_rule_set(db, rule_set_id, organization_id=organization_id)
    if row is None:
        return False
    if _rule_set_is_referenced(db, row.id):
        raise ValueError("Work time rule set is referenced by a plan version")
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="work_time_rule_set",
        entity_id=row.id,
    )
    db.delete(row)
    db.commit()
    return True
