from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    PlanningCell,
    PlanningDayStatusDefinition,
    PlanningPeriod,
    TeamMemberPlanningPattern,
)
from app.schemas import PlanningDayStatusDefinitionCreate, PlanningDayStatusDefinitionUpdate
from app.services.audit import record_audit

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

PLANNING_DAY_STATUS_COLOR_PRESETS = frozenset(
    {"rose", "violet", "amber", "slate", "emerald", "sky", "cyan", "orange", "lime", "fuchsia", "zinc", "indigo", "teal"}
)

DEFAULT_PLANNING_DAY_STATUSES: list[dict[str, Any]] = [
    {
        "code": "urlaub",
        "label": "Urlaub",
        "color_preset": "rose",
        "blocks_roster_assignment": True,
    },
    {
        "code": "forschung",
        "label": "Forschung",
        "color_preset": "violet",
        "blocks_roster_assignment": True,
    },
    {
        "code": "lehre",
        "label": "Lehre",
        "color_preset": "amber",
        "blocks_roster_assignment": True,
    },
    {
        "code": "frei",
        "label": "Frei",
        "color_preset": "slate",
        "blocks_roster_assignment": True,
    },
]


def normalize_planning_day_status_code(raw: str) -> str:
    code = raw.strip().lower()
    if not _CODE_RE.match(code):
        raise ValueError("Status code must start with a letter and use only lowercase letters, digits, and underscores")
    return code


def validate_color_preset(color_preset: str) -> str:
    preset = color_preset.strip().lower()
    if preset not in PLANNING_DAY_STATUS_COLOR_PRESETS:
        raise ValueError("Invalid color preset")
    return preset


def list_planning_day_status_definitions(
    db: Session, *, organization_id: int, active_only: bool = False
) -> list[PlanningDayStatusDefinition]:
    stmt = select(PlanningDayStatusDefinition).where(
        PlanningDayStatusDefinition.organization_id == organization_id
    )
    if active_only:
        stmt = stmt.where(PlanningDayStatusDefinition.is_active.is_(True))
    stmt = stmt.order_by(
        func.lower(PlanningDayStatusDefinition.label),
        PlanningDayStatusDefinition.code,
    )
    return list(db.scalars(stmt))


def get_planning_day_status_definition_or_none(
    db: Session, definition_id: int, *, organization_id: int
) -> PlanningDayStatusDefinition | None:
    row = db.get(PlanningDayStatusDefinition, definition_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def ensure_default_planning_day_statuses(db: Session, *, organization_id: int) -> None:
    existing = db.scalar(
        select(func.count())
        .select_from(PlanningDayStatusDefinition)
        .where(PlanningDayStatusDefinition.organization_id == organization_id)
    )
    if existing:
        return
    for item in DEFAULT_PLANNING_DAY_STATUSES:
        db.add(
            PlanningDayStatusDefinition(
                organization_id=organization_id,
                code=item["code"],
                label=item["label"],
                color_preset=item["color_preset"],
                blocks_roster_assignment=item["blocks_roster_assignment"],
                is_active=True,
            )
        )
    db.commit()


def active_planning_day_status_codes(db: Session, *, organization_id: int) -> set[str]:
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    rows = list_planning_day_status_definitions(db, organization_id=organization_id, active_only=True)
    return {row.code for row in rows}


def cell_status_blocks_roster_assignment(db: Session, *, organization_id: int, status: str) -> bool:
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    code = status.strip().lower()
    row = db.scalar(
        select(PlanningDayStatusDefinition).where(
            PlanningDayStatusDefinition.organization_id == organization_id,
            PlanningDayStatusDefinition.code == code,
        )
    )
    if row is None:
        return True
    return row.blocks_roster_assignment


def roster_blocking_planning_day_status_codes(db: Session, *, organization_id: int) -> set[str]:
    ensure_default_planning_day_statuses(db, organization_id=organization_id)
    rows = list_planning_day_status_definitions(db, organization_id=organization_id, active_only=False)
    return {row.code for row in rows if row.blocks_roster_assignment}


def assert_valid_planning_cell_status(db: Session, *, organization_id: int, status: str) -> None:
    code = normalize_planning_day_status_code(status)
    allowed = active_planning_day_status_codes(db, organization_id=organization_id)
    if code not in allowed:
        raise ValueError("Unknown or inactive planning day status")


def _definition_in_use(db: Session, definition: PlanningDayStatusDefinition) -> bool:
    cell_count = db.scalar(
        select(func.count())
        .select_from(PlanningCell)
        .join(PlanningPeriod, PlanningPeriod.id == PlanningCell.planning_period_id)
        .where(
            PlanningPeriod.organization_id == definition.organization_id,
            PlanningCell.status == definition.code,
        )
    )
    if cell_count:
        return True
    patterns = db.scalars(
        select(TeamMemberPlanningPattern).where(
            TeamMemberPlanningPattern.organization_id == definition.organization_id
        )
    )
    for pattern in patterns:
        rule = pattern.rule if isinstance(pattern.rule, dict) else {}
        if rule.get("status") == definition.code:
            return True
    return False


def create_planning_day_status_definition(
    db: Session,
    payload: PlanningDayStatusDefinitionCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> PlanningDayStatusDefinition:
    code = normalize_planning_day_status_code(payload.code)
    color_preset = validate_color_preset(payload.color_preset)
    existing = db.scalar(
        select(PlanningDayStatusDefinition).where(
            PlanningDayStatusDefinition.organization_id == organization_id,
            PlanningDayStatusDefinition.code == code,
        )
    )
    if existing is not None:
        raise ValueError("A day status with this code already exists")
    row = PlanningDayStatusDefinition(
        organization_id=organization_id,
        code=code,
        label=payload.label.strip(),
        color_preset=color_preset,
        blocks_roster_assignment=payload.blocks_roster_assignment,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="planning_day_status_definition",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


def update_planning_day_status_definition(
    db: Session,
    definition_id: int,
    payload: PlanningDayStatusDefinitionUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> PlanningDayStatusDefinition | None:
    row = get_planning_day_status_definition_or_none(db, definition_id, organization_id=organization_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "label" in data and data["label"] is not None:
        data["label"] = data["label"].strip()
    if "color_preset" in data and data["color_preset"] is not None:
        data["color_preset"] = validate_color_preset(data["color_preset"])
    for key, value in data.items():
        setattr(row, key, value)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="planning_day_status_definition",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


def delete_planning_day_status_definition(
    db: Session,
    definition_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> bool:
    row = get_planning_day_status_definition_or_none(db, definition_id, organization_id=organization_id)
    if row is None:
        return False
    active_count = db.scalar(
        select(func.count())
        .select_from(PlanningDayStatusDefinition)
        .where(
            PlanningDayStatusDefinition.organization_id == organization_id,
            PlanningDayStatusDefinition.is_active.is_(True),
        )
    )
    if row.is_active and active_count is not None and active_count <= 1:
        raise ValueError("At least one active day status is required")
    if _definition_in_use(db, row):
        raise ValueError("Day status is in use and cannot be deleted")
    record_audit(
        db,
        actor=actor,
        source=source,
        action="delete",
        entity_type="planning_day_status_definition",
        entity_id=row.id,
    )
    db.delete(row)
    db.commit()
    return True
