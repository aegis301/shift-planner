from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TeamMemberPropertyDefinition, TeamMemberPropertyValue
from app.schemas import TeamMemberPropertyDefinitionCreate, TeamMemberPropertyDefinitionUpdate
from app.services.audit import record_audit
from app.services.team_member_property_values import validate_property_value_for_definition

_SELECT_TYPES = frozenset({"select", "multi_select"})


def list_team_member_property_definitions(
    db: Session, *, organization_id: int, active_only: bool = False
) -> list[TeamMemberPropertyDefinition]:
    stmt = select(TeamMemberPropertyDefinition).where(
        TeamMemberPropertyDefinition.organization_id == organization_id
    )
    if active_only:
        stmt = stmt.where(TeamMemberPropertyDefinition.is_active.is_(True))
    stmt = stmt.order_by(TeamMemberPropertyDefinition.name)
    return list(db.scalars(stmt))


def get_team_member_property_definition_or_none(
    db: Session, definition_id: int, *, organization_id: int
) -> TeamMemberPropertyDefinition | None:
    row = db.get(TeamMemberPropertyDefinition, definition_id)
    if row is None or row.organization_id != organization_id:
        return None
    return row


def _definition_has_invalid_values_after_change(
    db: Session,
    definition: TeamMemberPropertyDefinition,
    *,
    new_type: str,
    new_options: list[str],
) -> bool:
    values = list(
        db.scalars(
            select(TeamMemberPropertyValue).where(
                TeamMemberPropertyValue.property_definition_id == definition.id,
                TeamMemberPropertyValue.value.isnot(None),
            )
        )
    )
    probe = TeamMemberPropertyDefinition(
        organization_id=definition.organization_id,
        name=definition.name,
        type=new_type,
        options=new_options,
        editable_by_team_member=definition.editable_by_team_member,
        display_order=definition.display_order,
        is_active=definition.is_active,
    )
    for row in values:
        try:
            validate_property_value_for_definition(probe, row.value)
        except ValueError:
            return True
    return False


def create_team_member_property_definition(
    db: Session,
    payload: TeamMemberPropertyDefinitionCreate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> TeamMemberPropertyDefinition:
    row = TeamMemberPropertyDefinition(
        organization_id=organization_id,
        name=payload.name.strip(),
        type=payload.type,
        options=list(payload.options),
        editable_by_team_member=payload.editable_by_team_member,
        display_order=payload.display_order,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="team_member_property_definition",
        entity_id=row.id,
    )
    db.commit()
    db.refresh(row)
    return row


def update_team_member_property_definition(
    db: Session,
    definition_id: int,
    payload: TeamMemberPropertyDefinitionUpdate,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> TeamMemberPropertyDefinition | None:
    row = get_team_member_property_definition_or_none(db, definition_id, organization_id=organization_id)
    if row is None:
        return None
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip()
    new_type = data.get("type", row.type)
    new_options = data["options"] if "options" in data else list(row.options or [])
    if new_type in _SELECT_TYPES and not new_options:
        raise ValueError("options are required for select and multi_select property types")
    if new_type not in _SELECT_TYPES and new_options:
        raise ValueError("options are only allowed for select and multi_select property types")
    if (
        new_type != row.type or new_options != list(row.options or [])
    ) and _definition_has_invalid_values_after_change(
        db, row, new_type=new_type, new_options=new_options
    ):
        raise ValueError("Cannot change type or options while member values would become invalid")
    for key, value in data.items():
        setattr(row, key, value)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="team_member_property_definition",
        entity_id=row.id,
        details=data,
    )
    db.commit()
    db.refresh(row)
    return row


def delete_team_member_property_definition(
    db: Session,
    definition_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> bool:
    row = get_team_member_property_definition_or_none(db, definition_id, organization_id=organization_id)
    if row is None:
        return False
    value_count = db.scalar(
        select(TeamMemberPropertyValue.id)
        .where(TeamMemberPropertyValue.property_definition_id == definition_id)
        .limit(1)
    )
    if value_count is not None:
        row.is_active = False
        db.flush()
        record_audit(
            db,
            actor=actor,
            source=source,
            action="deactivate",
            entity_type="team_member_property_definition",
            entity_id=row.id,
        )
    else:
        db.delete(row)
        record_audit(
            db,
            actor=actor,
            source=source,
            action="delete",
            entity_type="team_member_property_definition",
            entity_id=definition_id,
        )
    db.commit()
    return True
