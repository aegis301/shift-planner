from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TeamMember, TeamMemberPropertyDefinition, TeamMemberPropertyValue
from app.schemas import (
    TeamMemberPropertyDefinitionRead,
    TeamMemberPropertyMatrixCell,
    TeamMemberPropertyMatrixMember,
    TeamMemberPropertyValueRead,
    TeamMemberPropertyValuesMatrixRead,
    TeamMemberPropertyValuesReplace,
)
from app.services.audit import record_audit
from app.services.tenancy import require_team_member_in_org
from app.services.team_members import list_team_members

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SELECT_TYPES = frozenset({"select", "multi_select"})
_TEXT_MAX_LEN = 500


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    return isinstance(value, list) and len(value) == 0


def validate_property_value_for_definition(definition: TeamMemberPropertyDefinition, value: Any) -> Any:
    if _is_empty_value(value):
        return None
    prop_type = definition.type
    options = list(definition.options or [])
    if prop_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Property '{definition.name}' requires a number")
        return value
    if prop_type == "date":
        if not isinstance(value, str) or not _ISO_DATE_RE.match(value):
            raise ValueError(f"Property '{definition.name}' requires a date in YYYY-MM-DD format")
        date.fromisoformat(value)
        return value
    if prop_type == "text":
        if not isinstance(value, str):
            raise ValueError(f"Property '{definition.name}' requires text")
        text = value.strip()
        if not text:
            return None
        if len(text) > _TEXT_MAX_LEN:
            raise ValueError(f"Property '{definition.name}' text must be at most {_TEXT_MAX_LEN} characters")
        return text
    if prop_type == "select":
        if not isinstance(value, str):
            raise ValueError(f"Property '{definition.name}' requires a single option")
        if value not in options:
            raise ValueError(f"Property '{definition.name}' value is not an allowed option")
        return value
    if prop_type == "multi_select":
        if not isinstance(value, list):
            raise ValueError(f"Property '{definition.name}' requires a list of options")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"Property '{definition.name}' requires string options")
            if item in seen:
                continue
            if item not in options:
                raise ValueError(f"Property '{definition.name}' contains an invalid option")
            seen.add(item)
            normalized.append(item)
        if not normalized:
            return None
        return normalized
    raise ValueError(f"Unsupported property type: {prop_type}")


def _value_to_read(
    definition: TeamMemberPropertyDefinition,
    value_row: TeamMemberPropertyValue | None,
    *,
    organization_id: int,
    team_member_id: int,
) -> TeamMemberPropertyValueRead:
    return TeamMemberPropertyValueRead(
        id=value_row.id if value_row is not None else None,
        organization_id=organization_id,
        team_member_id=team_member_id,
        property_definition_id=definition.id,
        value=value_row.value if value_row is not None else None,
        name=definition.name,
        type=definition.type,
        options=list(definition.options or []),
        editable_by_team_member=definition.editable_by_team_member,
        display_order=definition.display_order,
        is_active=definition.is_active,
        created_at=value_row.created_at if value_row is not None else None,
        updated_at=value_row.updated_at if value_row is not None else None,
    )


def list_property_values_for_member(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    active_definitions_only: bool = False,
) -> list[TeamMemberPropertyValueRead]:
    require_team_member_in_org(db, team_member_id, organization_id)
    defs = list(
        db.scalars(
            select(TeamMemberPropertyDefinition)
            .where(TeamMemberPropertyDefinition.organization_id == organization_id)
            .order_by(TeamMemberPropertyDefinition.name)
        )
    )
    if active_definitions_only:
        defs = [row for row in defs if row.is_active]
    value_rows = {
        row.property_definition_id: row
        for row in db.scalars(
            select(TeamMemberPropertyValue).where(
                TeamMemberPropertyValue.team_member_id == team_member_id,
                TeamMemberPropertyValue.organization_id == organization_id,
            )
        )
    }
    return [
        _value_to_read(defn, value_rows.get(defn.id), organization_id=organization_id, team_member_id=team_member_id)
        for defn in defs
    ]


def property_value_dict_for_member(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
) -> dict[int, Any]:
    rows = db.scalars(
        select(TeamMemberPropertyValue).where(
            TeamMemberPropertyValue.team_member_id == team_member_id,
            TeamMemberPropertyValue.organization_id == organization_id,
        )
    ).all()
    return {row.property_definition_id: row.value for row in rows}


def property_value_maps_for_members(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: set[int],
) -> dict[int, dict[int, Any]]:
    if not team_member_ids:
        return {}
    rows = db.scalars(
        select(TeamMemberPropertyValue).where(
            TeamMemberPropertyValue.organization_id == organization_id,
            TeamMemberPropertyValue.team_member_id.in_(team_member_ids),
        )
    ).all()
    out: dict[int, dict[int, Any]] = {}
    for row in rows:
        out.setdefault(row.team_member_id, {})[row.property_definition_id] = row.value
    return out


def list_property_values_matrix(
    db: Session,
    *,
    organization_id: int,
    active_definitions_only: bool = True,
    active_members_only: bool = False,
) -> TeamMemberPropertyValuesMatrixRead:
    definitions = list(
        db.scalars(
            select(TeamMemberPropertyDefinition)
            .where(TeamMemberPropertyDefinition.organization_id == organization_id)
            .order_by(TeamMemberPropertyDefinition.name)
        )
    )
    if active_definitions_only:
        definitions = [row for row in definitions if row.is_active]
    members: list[TeamMember] = list_team_members(
        db, organization_id=organization_id, active_only=active_members_only
    )
    value_maps = property_value_maps_for_members(
        db,
        organization_id=organization_id,
        team_member_ids={member.id for member in members},
    )
    return TeamMemberPropertyValuesMatrixRead(
        definitions=[TeamMemberPropertyDefinitionRead.model_validate(row) for row in definitions],
        members=[
            TeamMemberPropertyMatrixMember(
                id=member.id,
                first_name=member.first_name,
                last_name=member.last_name,
                nickname=member.nickname,
                is_active=member.is_active,
                values=[
                    TeamMemberPropertyMatrixCell(
                        property_definition_id=defn.id,
                        value=value_maps.get(member.id, {}).get(defn.id),
                    )
                    for defn in definitions
                ],
            )
            for member in members
        ],
    )


def replace_team_member_property_values(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    payload: TeamMemberPropertyValuesReplace,
    actor: str,
    source: str,
    allow_definition_ids: set[int] | None = None,
) -> list[TeamMemberPropertyValueRead]:
    require_team_member_in_org(db, team_member_id, organization_id)
    definitions = {
        row.id: row
        for row in db.scalars(
            select(TeamMemberPropertyDefinition).where(
                TeamMemberPropertyDefinition.organization_id == organization_id
            )
        )
    }
    existing = {
        row.property_definition_id: row
        for row in db.scalars(
            select(TeamMemberPropertyValue).where(
                TeamMemberPropertyValue.team_member_id == team_member_id,
                TeamMemberPropertyValue.organization_id == organization_id,
            )
        )
    }
    touched_def_ids: set[int] = set()
    for item in payload.values:
        defn = definitions.get(item.property_definition_id)
        if defn is None:
            raise ValueError(f"Unknown property definition id {item.property_definition_id}")
        if allow_definition_ids is not None and defn.id not in allow_definition_ids:
            raise PermissionError(f"Not allowed to edit property '{defn.name}'")
        touched_def_ids.add(defn.id)
        normalized = validate_property_value_for_definition(defn, item.value)
        row = existing.get(defn.id)
        if normalized is None:
            if row is not None:
                record_audit(
                    db,
                    actor=actor,
                    source=source,
                    action="delete",
                    entity_type="team_member_property_value",
                    entity_id=row.id,
                    details={"property_definition_id": defn.id, "team_member_id": team_member_id},
                )
                db.delete(row)
                existing.pop(defn.id, None)
            continue
        if row is None:
            row = TeamMemberPropertyValue(
                organization_id=organization_id,
                team_member_id=team_member_id,
                property_definition_id=defn.id,
                value=normalized,
            )
            db.add(row)
            db.flush()
            existing[defn.id] = row
            record_audit(
                db,
                actor=actor,
                source=source,
                action="create",
                entity_type="team_member_property_value",
                entity_id=row.id,
                details={"property_definition_id": defn.id, "team_member_id": team_member_id},
            )
        elif row.value != normalized:
            row.value = normalized
            db.flush()
            record_audit(
                db,
                actor=actor,
                source=source,
                action="update",
                entity_type="team_member_property_value",
                entity_id=row.id,
                details={"property_definition_id": defn.id, "team_member_id": team_member_id},
            )
    db.commit()
    return list_property_values_for_member(
        db,
        team_member_id=team_member_id,
        organization_id=organization_id,
        active_definitions_only=False,
    )
