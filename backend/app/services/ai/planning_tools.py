from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.services.matrix import get_planning_matrix, list_team_member_period_notes
from app.services.mcp_access import McpPrincipal
from app.services.roster_matrix import get_roster_matrix
from app.services.team_members import list_team_members, team_member_planning_display_name
from app.services.validation import validate_roster
from app.services.workload import (
    WorkloadAssignmentSlice,
    WorkloadMemberSlice,
    WorkloadSlotSlice,
    build_member_workload_rows,
)

ToolHandler = Callable[..., Any]


def _assert_scope(db: Session, principal: McpPrincipal, shift_group_id: int | None) -> None:
    if principal.is_admin:
        if shift_group_id is None:
            return
        from app.models import ShiftGroup

        group = db.get(ShiftGroup, shift_group_id)
        if group is None or group.organization_id != principal.organization_id:
            raise PermissionError("Shift group not found")
        return
    if shift_group_id is None:
        raise PermissionError("shift_group_id is required")
    if shift_group_id not in principal.shift_group_ids:
        raise PermissionError("Not a member of this shift group")


def tool_get_planning_matrix(
    db: Session,
    principal: McpPrincipal,
    *,
    planning_period_id: int,
    shift_group_id: int | None = None,
) -> dict[str, Any]:
    _assert_scope(db, principal, shift_group_id)
    return get_planning_matrix(
        db,
        planning_period_id,
        organization_id=principal.organization_id,
        shift_group_id=shift_group_id,
    ).model_dump(mode="json")


def tool_get_roster_matrix(
    db: Session,
    principal: McpPrincipal,
    *,
    planning_period_id: int,
    shift_group_id: int | None = None,
) -> dict[str, Any]:
    _assert_scope(db, principal, shift_group_id)
    return get_roster_matrix(
        db,
        planning_period_id,
        organization_id=principal.organization_id,
        shift_group_id=shift_group_id,
    ).model_dump(mode="json")


def tool_get_validation_warnings(
    db: Session,
    principal: McpPrincipal,
    *,
    planning_period_id: int,
    shift_group_id: int | None = None,
) -> list[dict[str, Any]]:
    _assert_scope(db, principal, shift_group_id)
    return [
        warning.model_dump(mode="json")
        for warning in validate_roster(
            db,
            planning_period_id,
            organization_id=principal.organization_id,
            shift_group_id=shift_group_id,
        )
    ]


def tool_list_team_members(
    db: Session,
    principal: McpPrincipal,
    *,
    shift_group_id: int | None = None,
) -> list[dict[str, Any]]:
    _assert_scope(db, principal, shift_group_id)
    members = list_team_members(db, organization_id=principal.organization_id)
    rows = []
    for member in members:
        group_ids = sorted({link.shift_group_id for link in member.shift_group_links})
        if shift_group_id is not None and shift_group_id not in group_ids:
            continue
        rows.append(
            {
                "id": member.id,
                "display_name": team_member_planning_display_name(member),
                "first_name": member.first_name,
                "last_name": member.last_name,
                "nickname": member.nickname,
                "employment_percentage": member.employment_percentage,
                "shift_group_ids": group_ids,
            }
        )
    return rows


def tool_list_period_notes(
    db: Session,
    principal: McpPrincipal,
    *,
    planning_period_id: int,
    shift_group_id: int | None = None,
) -> list[dict[str, Any]]:
    _assert_scope(db, principal, shift_group_id)
    notes = list_team_member_period_notes(
        db,
        planning_period_id=planning_period_id,
        organization_id=principal.organization_id,
        shift_group_id=shift_group_id,
    )
    return [
        {
            "team_member_id": note.team_member_id,
            "shift_group_id": note.shift_group_id,
            "summary": note.summary,
        }
        for note in notes
    ]


def tool_get_member_workload(
    db: Session,
    principal: McpPrincipal,
    *,
    planning_period_id: int,
    shift_group_id: int | None = None,
) -> dict[str, Any]:
    _assert_scope(db, principal, shift_group_id)
    roster = get_roster_matrix(
        db,
        planning_period_id,
        organization_id=principal.organization_id,
        shift_group_id=shift_group_id,
    )
    warnings = validate_roster(
        db,
        planning_period_id,
        organization_id=principal.organization_id,
        shift_group_id=shift_group_id,
    )
    slots = [
        WorkloadSlotSlice(
            id=slot.id,
            shift_template_id=slot.shift_template_id,
            category=slot.category,
            slot_date=slot.slot_date,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
        )
        for slot in roster.slots
    ]
    assignments = [
        WorkloadAssignmentSlice(roster_slot_id=row.roster_slot_id, team_member_id=row.team_member_id)
        for row in roster.assignments
    ]
    members = [
        WorkloadMemberSlice(
            id=member.id,
            first_name=member.first_name,
            last_name=member.last_name,
            nickname=member.nickname,
            employment_percentage=member.employment_percentage,
        )
        for member in roster.team_members
    ]
    rows, unassigned = build_member_workload_rows(
        slots=slots,
        assignments=assignments,
        members=members,
        warnings=warnings,
    )
    return {
        "unassigned": unassigned,
        "rows": [
            {
                "team_member_id": row.team_member_id,
                "name": row.name,
                "employment_percentage": row.employment_percentage,
                "total": row.total,
                "on_call_duty": row.on_call_duty,
                "standby_duty": row.standby_duty,
                "late_duty": row.late_duty,
                "other": row.other,
                "weekend_holiday_shifts": row.weekend_holiday_shifts,
                "conflicts": row.conflicts,
            }
            for row in rows
        ],
    }


READ_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_planning_matrix",
        "description": "Wishes matrix for a planning month (day statuses, comments, wish/no-go intents).",
        "handler": tool_get_planning_matrix,
        "parameters": {
            "type": "object",
            "properties": {
                "planning_period_id": {"type": "integer"},
                "shift_group_id": {"type": "integer"},
            },
            "required": ["planning_period_id"],
        },
    },
    {
        "name": "get_roster_matrix",
        "description": "Final roster slots and assignments for a planning month.",
        "handler": tool_get_roster_matrix,
        "parameters": {
            "type": "object",
            "properties": {
                "planning_period_id": {"type": "integer"},
                "shift_group_id": {"type": "integer"},
            },
            "required": ["planning_period_id"],
        },
    },
    {
        "name": "get_validation_warnings",
        "description": "Structured roster and wishes validation warnings.",
        "handler": tool_get_validation_warnings,
        "parameters": {
            "type": "object",
            "properties": {
                "planning_period_id": {"type": "integer"},
                "shift_group_id": {"type": "integer"},
            },
            "required": ["planning_period_id"],
        },
    },
    {
        "name": "list_team_members",
        "description": "Team members visible for planning (ids, display names, employment).",
        "handler": tool_list_team_members,
        "parameters": {
            "type": "object",
            "properties": {"shift_group_id": {"type": "integer"}},
        },
    },
    {
        "name": "list_period_notes",
        "description": "Month summary notes per team member.",
        "handler": tool_list_period_notes,
        "parameters": {
            "type": "object",
            "properties": {
                "planning_period_id": {"type": "integer"},
                "shift_group_id": {"type": "integer"},
            },
            "required": ["planning_period_id"],
        },
    },
    {
        "name": "get_member_workload",
        "description": "Shift-count workload per team member for the month.",
        "handler": tool_get_member_workload,
        "parameters": {
            "type": "object",
            "properties": {
                "planning_period_id": {"type": "integer"},
                "shift_group_id": {"type": "integer"},
            },
            "required": ["planning_period_id"],
        },
    },
]

READ_TOOLS_BY_NAME = {spec["name"]: spec for spec in READ_TOOL_SPECS}

TASK_TOOL_ALLOWLIST = {
    "summarize_wishes": (
        "get_planning_matrix",
        "list_period_notes",
        "list_team_members",
    ),
    "explain_validation": (
        "get_validation_warnings",
        "get_roster_matrix",
        "get_planning_matrix",
        "list_team_members",
    ),
    "draft_fair_roster": (
        "get_roster_matrix",
        "get_planning_matrix",
        "get_validation_warnings",
        "get_member_workload",
        "list_team_members",
        "list_period_notes",
    ),
}


def invoke_read_tool(
    db: Session,
    principal: McpPrincipal,
    name: str,
    arguments: dict[str, Any],
    *,
    allowed: set[str],
) -> Any:
    if name not in allowed:
        raise PermissionError(f"Tool {name} is not allowed for this task")
    spec = READ_TOOLS_BY_NAME.get(name)
    if spec is None:
        raise ValueError(f"Unknown tool {name}")
    handler: ToolHandler = spec["handler"]
    allowed_names = set(inspect.signature(handler).parameters) - {"db", "principal"}
    cleaned = {key: value for key, value in arguments.items() if key in allowed_names}
    for key, value in list(cleaned.items()):
        if key.endswith("_id") and value is not None and value != "":
            cleaned[key] = int(value)
    return handler(db, principal, **cleaned)
