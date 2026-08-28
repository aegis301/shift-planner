from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import TeamMemberPropertyDefinition
from app.schemas import (
    TeamMemberPropertyDefinitionRead,
    TeamMemberPropertyMatrixFilter,
    TeamMemberPropertyMatrixMember,
    TeamMemberPropertyMatrixRead,
    TeamMemberPropertyMatrixValue,
)
from app.services.team_member_property_definitions import list_team_member_property_definitions
from app.services.team_member_property_values import property_value_maps_for_members
from app.services.team_members import list_team_members

_COMMON_OPERATORS = frozenset({"is_empty", "is_not_empty"})
_OPERATORS_BY_TYPE = {
    "text": frozenset({"contains", "equals"}),
    "select": frozenset({"equals", "not_equals"}),
    "multi_select": frozenset({"contains_any", "contains_all"}),
    "number": frozenset(
        {"equals", "greater_than", "greater_or_equal", "less_than", "less_or_equal"}
    ),
    "date": frozenset(
        {"equals", "before", "on_or_before", "after", "on_or_after"}
    ),
}


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _validated_filter_value(
    definition: TeamMemberPropertyDefinition,
    property_filter: TeamMemberPropertyMatrixFilter,
) -> Any:
    operator = property_filter.operator
    allowed = _COMMON_OPERATORS | _OPERATORS_BY_TYPE.get(definition.type, frozenset())
    if operator not in allowed:
        raise ValueError(
            f"Operator '{operator}' is not valid for property '{definition.name}'"
        )
    if operator in _COMMON_OPERATORS:
        return None
    value = property_filter.value
    if definition.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Filter for property '{definition.name}' requires a number")
        return value
    if definition.type == "date":
        if not isinstance(value, str):
            raise ValueError(f"Filter for property '{definition.name}' requires a date")
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"Filter for property '{definition.name}' requires a date in YYYY-MM-DD format"
            ) from exc
    if definition.type in {"text", "select"}:
        if not isinstance(value, str) or not value:
            raise ValueError(f"Filter for property '{definition.name}' requires text")
        if definition.type == "select" and value not in list(definition.options or []):
            raise ValueError(
                f"Filter for property '{definition.name}' requires an allowed option"
            )
        return value
    if definition.type == "multi_select":
        options = list(definition.options or [])
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or item not in options for item in value)
        ):
            raise ValueError(
                f"Filter for property '{definition.name}' requires allowed options"
            )
        return list(dict.fromkeys(value))
    raise ValueError(f"Unsupported property type: {definition.type}")


def _matches_filter(
    definition: TeamMemberPropertyDefinition,
    property_filter: TeamMemberPropertyMatrixFilter,
    value: Any,
) -> bool:
    operator = property_filter.operator
    expected = _validated_filter_value(definition, property_filter)
    if operator == "is_empty":
        return _is_empty(value)
    if operator == "is_not_empty":
        return not _is_empty(value)
    if definition.type == "text":
        if not isinstance(value, str):
            return False
        if operator == "contains":
            return expected.casefold() in value.casefold()
        return value.casefold() == expected.casefold()
    if definition.type == "select":
        if operator == "not_equals":
            return value != expected
        return value == expected
    if definition.type == "multi_select":
        selected = set(value) if isinstance(value, list) else set()
        expected_options = set(expected)
        if operator == "contains_any":
            return bool(selected & expected_options)
        return expected_options <= selected
    if definition.type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if operator == "equals":
            return value == expected
        if operator == "greater_than":
            return value > expected
        if operator == "greater_or_equal":
            return value >= expected
        if operator == "less_than":
            return value < expected
        return value <= expected
    if definition.type == "date":
        if not isinstance(value, str):
            return False
        try:
            actual_date = date.fromisoformat(value)
        except ValueError:
            return False
        if operator == "equals":
            return actual_date == expected
        if operator == "before":
            return actual_date < expected
        if operator == "on_or_before":
            return actual_date <= expected
        if operator == "after":
            return actual_date > expected
        return actual_date >= expected
    return False


def get_team_member_property_matrix(
    db: Session,
    *,
    organization_id: int,
    active_members_only: bool = True,
    active_definitions_only: bool = True,
    filters: list[TeamMemberPropertyMatrixFilter] | None = None,
) -> TeamMemberPropertyMatrixRead:
    definitions = sorted(
        list_team_member_property_definitions(
            db,
            organization_id=organization_id,
            active_only=active_definitions_only,
        ),
        key=lambda definition: (definition.display_order, definition.name.casefold(), definition.id),
    )
    members = list_team_members(
        db,
        organization_id=organization_id,
        active_only=active_members_only,
    )
    member_ids = {member.id for member in members}
    value_maps = property_value_maps_for_members(
        db,
        organization_id=organization_id,
        team_member_ids=member_ids,
    )
    definitions_by_id = {definition.id: definition for definition in definitions}
    active_filters = filters or []
    for property_filter in active_filters:
        definition = definitions_by_id.get(property_filter.property_definition_id)
        if definition is None:
            raise ValueError(
                f"Unknown property definition id {property_filter.property_definition_id}"
            )
        _validated_filter_value(definition, property_filter)
    if active_filters:
        members = [
            member
            for member in members
            if all(
                _matches_filter(
                    definitions_by_id[property_filter.property_definition_id],
                    property_filter,
                    value_maps.get(member.id, {}).get(
                        property_filter.property_definition_id
                    ),
                )
                for property_filter in active_filters
            )
        ]
        member_ids = {member.id for member in members}
    definition_ids = {definition.id for definition in definitions}
    values = [
        TeamMemberPropertyMatrixValue(
            team_member_id=team_member_id,
            property_definition_id=definition_id,
            value=value,
        )
        for team_member_id, member_values in value_maps.items()
        for definition_id, value in member_values.items()
        if team_member_id in member_ids and definition_id in definition_ids
    ]
    values.sort(key=lambda value: (value.team_member_id, value.property_definition_id))
    return TeamMemberPropertyMatrixRead(
        definitions=[
            TeamMemberPropertyDefinitionRead.model_validate(definition)
            for definition in definitions
        ],
        members=[
            TeamMemberPropertyMatrixMember(
                id=member.id,
                first_name=member.first_name,
                last_name=member.last_name,
                nickname=member.nickname,
                is_active=member.is_active,
            )
            for member in members
        ],
        values=values,
    )
