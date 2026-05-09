from contextlib import contextmanager
from datetime import date, time
import os
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import ShiftGroup
from app.schemas import (
    TeamMemberCreate,
    TeamMemberPeriodNoteUpsert,
    PlanningCellBulkUpsert,
    PlanningCellUpsert,
    PlanningPeriodCreate,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentUpsert,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentUpsert,
    ShiftGroupCreate,
    ShiftTemplateCreate,
    ShiftTemplateUpdate,
    ShiftVariantCreate,
    ShiftVariantUpdate,
)
from app.services.team_members import create_team_member, delete_team_member, list_team_members
from app.services.matrix import (
    bulk_upsert_planning_cells,
    bulk_upsert_planning_shift_intents,
    get_planning_matrix,
    list_team_member_period_notes,
    save_team_member_period_note,
    upsert_planning_cell,
)
from app.services.planning import (
    create_planning_period,
    delete_planning_period,
    list_planning_periods,
)
from app.services.roster_matrix import (
    clear_roster_slot_assignment,
    get_roster_matrix,
    reset_roster_slots_for_period,
    upsert_roster_slot_assignment,
)
from app.services.shift_groups import (
    create_shift_group,
    list_shift_groups,
    replace_group_team_members,
    replace_group_shift_templates,
)
from app.services.shift_templates import (
    ShiftTemplateCodeConflictError,
    create_shift_template,
    create_shift_variant,
    delete_shift_template,
    delete_shift_variant,
    list_shift_templates,
    preview_slots_for_month,
    update_shift_template,
    update_shift_variant,
)
from app.services.validation import validate_roster

mcp = FastMCP("Shift Planner")


@contextmanager
def db_session():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_token(token: str) -> None:
    if token != settings.mcp_admin_token:
        raise PermissionError("Invalid MCP admin token")


def mcp_organization_id() -> int:
    if settings.mcp_organization_id is not None:
        return settings.mcp_organization_id
    return settings.default_organization_id


def serialize_model(model: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for column in model.__table__.columns:
        value = getattr(model, column.name)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        output[column.name] = value
    return output


@mcp.tool
def health() -> dict[str, str]:
    """Return MCP server health."""
    return {"status": "ok", "service": "shift-planner-mcp"}


@mcp.resource("shift-planner://team-members")
def team_members_resource() -> list[dict[str, Any]]:
    """List all team members in the default organization."""
    with db_session() as db:
        return [
            {
                **serialize_model(member),
                "shift_group_ids": sorted({link.shift_group_id for link in member.shift_group_links}),
            }
            for member in list_team_members(db, organization_id=mcp_organization_id())
        ]


@mcp.resource("shift-planner://shift-templates")
def shift_templates_resource() -> list[dict[str, Any]]:
    """List all shift templates with variant metadata."""
    with db_session() as db:
        return [
            {
                **serialize_model(template),
                "variants": [serialize_model(variant) for variant in template.variants],
            }
            for template in list_shift_templates(db, organization_id=mcp_organization_id())
        ]


@mcp.resource("shift-planner://planning-periods")
def planning_periods_resource() -> list[dict[str, Any]]:
    """List monthly planning periods."""
    with db_session() as db:
        return [
            serialize_model(period) for period in list_planning_periods(db, organization_id=mcp_organization_id())
        ]


@mcp.resource("shift-planner://shift-groups")
def shift_groups_resource() -> list[dict[str, Any]]:
    """List shift groups with team member and shift template membership ids (`team_member_ids` in payload)."""
    with db_session() as db:
        return [
            {
                **serialize_model(group),
                "team_member_ids": sorted({link.team_member_id for link in group.team_member_links}),
                "shift_template_ids": sorted({link.shift_template_id for link in group.template_links}),
            }
            for group in list_shift_groups(db, organization_id=mcp_organization_id())
        ]


@mcp.resource("shift-planner://matrix/{planning_period_id}")
def matrix_resource(planning_period_id: int) -> dict[str, Any]:
    """Return the monthly planning matrix with days, `team_members`, and cells."""
    with db_session() as db:
        return get_planning_matrix(
            db, planning_period_id, organization_id=mcp_organization_id()
        ).model_dump(mode="json")


@mcp.resource("shift-planner://matrix/{planning_period_id}/shift-group/{shift_group_id}")
def matrix_filtered_resource(planning_period_id: int, shift_group_id: int) -> dict[str, Any]:
    """Return the planning matrix filtered to one shift group."""
    with db_session() as db:
        return get_planning_matrix(
            db, planning_period_id, organization_id=mcp_organization_id(), shift_group_id=shift_group_id
        ).model_dump(mode="json")


@mcp.resource("shift-planner://roster-matrix/{planning_period_id}")
def roster_matrix_resource(planning_period_id: int) -> dict[str, Any]:
    """Return the final roster matrix with days, shift slots, `team_members`, and assignments."""
    with db_session() as db:
        return get_roster_matrix(db, planning_period_id, organization_id=mcp_organization_id()).model_dump(
            mode="json"
        )


@mcp.resource("shift-planner://roster-matrix/{planning_period_id}/shift-group/{shift_group_id}")
def roster_matrix_filtered_resource(planning_period_id: int, shift_group_id: int) -> dict[str, Any]:
    """Return the final roster matrix filtered to one shift group."""
    with db_session() as db:
        return get_roster_matrix(
            db, planning_period_id, organization_id=mcp_organization_id(), shift_group_id=shift_group_id
        ).model_dump(mode="json")


@mcp.resource("shift-planner://team-member-period-notes/{planning_period_id}")
def team_member_period_notes_resource(planning_period_id: int) -> list[dict[str, Any]]:
    """Return monthly notes per team member for a planning period."""
    with db_session() as db:
        return [
            serialize_model(note)
            for note in list_team_member_period_notes(
                db, planning_period_id=planning_period_id, organization_id=mcp_organization_id()
            )
        ]


@mcp.resource("shift-planner://team-member-period-notes/{planning_period_id}/shift-group/{shift_group_id}")
def team_member_period_notes_filtered_resource(planning_period_id: int, shift_group_id: int) -> list[dict[str, Any]]:
    """Return period notes filtered to team members in a shift group."""
    with db_session() as db:
        return [
            serialize_model(note)
            for note in list_team_member_period_notes(
                db,
                planning_period_id=planning_period_id,
                organization_id=mcp_organization_id(),
                shift_group_id=shift_group_id,
            )
        ]


@mcp.tool
def get_validation_warnings(planning_period_id: int, shift_group_id: int | None = None) -> list[dict[str, Any]]:
    """Validate a planning period and return structured warnings. Optionally filter to one shift group."""
    with db_session() as db:
        return [
            warning.model_dump(mode="json")
            for warning in validate_roster(
                db, planning_period_id, organization_id=mcp_organization_id(), shift_group_id=shift_group_id
            )
        ]


@mcp.tool
def create_team_member_tool(
    token: str,
    first_name: str,
    last_name: str,
    email: str,
    employment_percentage: int = 100,
    notes: str | None = None,
    shift_group_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Create a team member row. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        member = create_team_member(
            db,
            TeamMemberCreate(
                first_name=first_name,
                last_name=last_name,
                email=email,
                employment_percentage=employment_percentage,
                notes=notes,
                shift_group_ids=list(shift_group_ids or []),
            ),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        db.refresh(member, attribute_names=["shift_group_links"])
        return {
            **serialize_model(member),
            "shift_group_ids": sorted({link.shift_group_id for link in member.shift_group_links}),
        }


@mcp.tool
def create_shift_group_tool(
    token: str,
    code: str,
    name_de: str,
    name_en: str,
    display_order: int = 0,
    is_active: bool = True,
) -> dict[str, Any]:
    """Create a shift group. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        group = create_shift_group(
            db,
            ShiftGroupCreate(code=code, name_de=name_de, name_en=name_en, display_order=display_order, is_active=is_active),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        db.refresh(group, attribute_names=["team_member_links", "template_links"])
        return {
            **serialize_model(group),
            "team_member_ids": sorted({link.team_member_id for link in group.team_member_links}),
            "shift_template_ids": sorted({link.shift_template_id for link in group.template_links}),
        }


@mcp.tool
def set_shift_group_team_members_tool(token: str, shift_group_id: int, team_member_ids: list[int]) -> dict[str, Any]:
    """Replace team members assigned to a shift group. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        replace_group_team_members(
            db, shift_group_id, team_member_ids, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
        )
        match = db.get(ShiftGroup, shift_group_id)
        if match is None:
            return {"shift_group_id": shift_group_id, "team_member_ids": [], "shift_template_ids": []}
        db.refresh(match, attribute_names=["team_member_links", "template_links"])
        return {
            **serialize_model(match),
            "team_member_ids": sorted({link.team_member_id for link in match.team_member_links}),
            "shift_template_ids": sorted({link.shift_template_id for link in match.template_links}),
        }


@mcp.tool
def set_shift_group_templates_tool(token: str, shift_group_id: int, shift_template_ids: list[int]) -> dict[str, Any]:
    """Replace shift templates covered by a shift group. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        replace_group_shift_templates(
            db, shift_group_id, shift_template_ids, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
        )
        match = db.get(ShiftGroup, shift_group_id)
        if match is None:
            return {"shift_group_id": shift_group_id, "team_member_ids": [], "shift_template_ids": []}
        db.refresh(match, attribute_names=["team_member_links", "template_links"])
        return {
            **serialize_model(match),
            "team_member_ids": sorted({link.team_member_id for link in match.team_member_links}),
            "shift_template_ids": sorted({link.shift_template_id for link in match.template_links}),
        }


@mcp.tool
def delete_team_member_tool(token: str, team_member_id: int) -> dict[str, bool]:
    """Delete a team member and clear related wishes, notes, and assignments. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        return {
            "deleted": delete_team_member(
                db, team_member_id, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
            )
        }


@mcp.tool
def create_shift_template_tool(
    token: str,
    code: str,
    name_de: str,
    name_en: str,
    category: str = "bereitschaftsdienst",
    display_order: int = 0,
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a shift template. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        try:
            template = create_shift_template(
                db,
                ShiftTemplateCreate(
                    code=code,
                    name_de=name_de,
                    name_en=name_en,
                    category=category,  # type: ignore[arg-type]
                    display_order=display_order,
                    constraints=constraints or [],
                ),
                organization_id=mcp_organization_id(),
                actor="mcp",
                source="mcp",
            )
        except ShiftTemplateCodeConflictError as exc:
            raise ValueError(f"Shift template code already exists: {exc.code}") from exc
        return serialize_model(template)


@mcp.tool
def update_shift_template_tool(
    token: str,
    shift_template_id: int,
    code: str | None = None,
    name_de: str | None = None,
    name_en: str | None = None,
    category: str | None = None,
    display_order: int | None = None,
    is_active: bool | None = None,
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Update a shift template. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        try:
            template = update_shift_template(
                db,
                shift_template_id,
                ShiftTemplateUpdate(
                    code=code,
                    name_de=name_de,
                    name_en=name_en,
                    category=category,  # type: ignore[arg-type]
                    display_order=display_order,
                    is_active=is_active,
                    constraints=constraints,
                ),
                organization_id=mcp_organization_id(),
                actor="mcp",
                source="mcp",
            )
        except ShiftTemplateCodeConflictError as exc:
            raise ValueError(f"Shift template code already exists: {exc.code}") from exc
        if template is None:
            raise ValueError("Shift template not found")
        return serialize_model(template)


@mcp.tool
def delete_shift_template_tool(token: str, shift_template_id: int) -> dict[str, bool]:
    """Delete a shift template, its variants, generated slots, and assignments. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        return {
            "deleted": delete_shift_template(
                db, shift_template_id, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
            )
        }


@mcp.tool
def create_shift_variant_tool(
    token: str,
    shift_template_id: int,
    label: str,
    start_day_class: str,
    starts_at: str,
    ends_at: str,
    end_day_class: str | None = None,
    end_day_offset: int = 0,
    required_count: int = 1,
    constraints: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a shift template variant. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        variant = create_shift_variant(
            db,
            shift_template_id,
            ShiftVariantCreate(
                label=label,
                start_day_class=start_day_class,  # type: ignore[arg-type]
                end_day_class=end_day_class,  # type: ignore[arg-type]
                starts_at=time.fromisoformat(starts_at),
                ends_at=time.fromisoformat(ends_at),
                end_day_offset=end_day_offset,
                required_count=required_count,
                constraints=constraints or [],
            ),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        if variant is None:
            raise ValueError("Shift template not found")
        return serialize_model(variant)


@mcp.tool
def update_shift_variant_tool(
    token: str,
    shift_variant_id: int,
    label: str | None = None,
    start_day_class: str | None = None,
    end_day_class: str | None = None,
    starts_at: str | None = None,
    ends_at: str | None = None,
    end_day_offset: int | None = None,
    required_count: int | None = None,
    constraints: list[dict[str, Any]] | None = None,
    is_active: bool | None = None,
) -> dict[str, Any]:
    """Update a shift template variant. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        variant = update_shift_variant(
            db,
            shift_variant_id,
            ShiftVariantUpdate(
                label=label,
                start_day_class=start_day_class,  # type: ignore[arg-type]
                end_day_class=end_day_class,  # type: ignore[arg-type]
                starts_at=time.fromisoformat(starts_at) if starts_at else None,
                ends_at=time.fromisoformat(ends_at) if ends_at else None,
                end_day_offset=end_day_offset,
                required_count=required_count,
                constraints=constraints,
                is_active=is_active,
            ),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        if variant is None:
            raise ValueError("Shift variant not found")
        return serialize_model(variant)


@mcp.tool
def preview_shift_slots_tool(year: int, month: int) -> list[dict[str, Any]]:
    """Preview generated concrete roster slots for a month."""
    with db_session() as db:
        return [
            slot.model_dump(mode="json")
            for slot in preview_slots_for_month(
                db, year=year, month=month, organization_id=mcp_organization_id()
            )
        ]


@mcp.tool
def create_planning_period_tool(token: str, year: int, month: int) -> dict[str, Any]:
    """Create or return a monthly planning period. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        period = create_planning_period(
            db,
            PlanningPeriodCreate(year=year, month=month),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(period)


@mcp.tool
def regenerate_planning_period_roster_tool(token: str, planning_period_id: int) -> dict[str, Any]:
    """Delete roster slots and assignments for a period, then regenerate slots from current templates."""
    require_token(token)
    with db_session() as db:
        reset_roster_slots_for_period(
            db, planning_period_id, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
        )
        return get_roster_matrix(db, planning_period_id, organization_id=mcp_organization_id()).model_dump(
            mode="json"
        )


@mcp.tool
def delete_planning_period_tool(token: str, planning_period_id: int) -> dict[str, bool]:
    """Delete a planning period and all related wishes, notes, roster slots, and assignments."""
    require_token(token)
    with db_session() as db:
        return {
            "deleted": delete_planning_period(
                db, planning_period_id, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
            )
        }


@mcp.tool
def upsert_planning_cell_tool(
    token: str,
    planning_period_id: int,
    team_member_id: int,
    cell_date: str,
    status: str,
    comment: str | None = None,
) -> dict[str, Any]:
    """Set one matrix cell status/comment. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        cell = upsert_planning_cell(
            db,
            planning_period_id,
            PlanningCellUpsert(
                team_member_id=team_member_id,
                cell_date=date.fromisoformat(cell_date),
                status=status,  # type: ignore[arg-type]
                comment=comment,
            ),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(cell)


@mcp.tool
def bulk_upsert_planning_cells_tool(
    token: str,
    planning_period_id: int,
    cells: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Set multiple matrix cells atomically. Requires MCP admin token."""
    require_token(token)
    payload = PlanningCellBulkUpsert(
        cells=[
            PlanningCellUpsert(
                team_member_id=int(cell["team_member_id"]),
                cell_date=date.fromisoformat(str(cell["cell_date"])),
                status=str(cell["status"]),  # type: ignore[arg-type]
                comment=cell.get("comment"),
            )
            for cell in cells
        ]
    )
    with db_session() as db:
        return [
            serialize_model(cell)
            for cell in bulk_upsert_planning_cells(
                db, planning_period_id, payload, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
            )
        ]


@mcp.tool
def bulk_upsert_planning_shift_intents_tool(
    token: str,
    planning_period_id: int,
    intents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create, update, or clear per-shift-group wish/no-go rows (kind null clears). Requires MCP admin token."""
    require_token(token)
    intent_rows: list[PlanningShiftIntentUpsert] = []
    for row in intents:
        raw_kind = row.get("kind")
        kind: str | None = str(raw_kind) if raw_kind is not None else None
        intent_rows.append(
            PlanningShiftIntentUpsert(
                team_member_id=int(row["team_member_id"]),
                cell_date=date.fromisoformat(str(row["cell_date"])),
                shift_group_id=int(row["shift_group_id"]),
                shift_template_id=int(row["shift_template_id"]),
                kind=kind,  # type: ignore[arg-type]
            )
        )
    payload = PlanningShiftIntentBulkUpsert(intents=intent_rows)
    with db_session() as db:
        return [
            serialize_model(item)
            for item in bulk_upsert_planning_shift_intents(
                db, planning_period_id, payload, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
            )
        ]


@mcp.tool
def save_team_member_period_note_tool(
    token: str,
    planning_period_id: int,
    team_member_id: int,
    summary: str | None = None,
    wishes_response_received: bool = False,
    planning_preferences: str | None = None,
    sync_planning_preferences: bool = False,
) -> dict[str, Any]:
    """Save a team member's monthly matrix note; optionally sync permanent planning preferences on the team member. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        note = save_team_member_period_note(
            db,
            planning_period_id,
            TeamMemberPeriodNoteUpsert(
                team_member_id=team_member_id,
                summary=summary,
                wishes_response_received=wishes_response_received,
                planning_preferences=planning_preferences,
                sync_planning_preferences=sync_planning_preferences,
            ),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(note)


@mcp.tool
def upsert_roster_slot_assignment_tool(
    token: str,
    roster_slot_id: int,
    team_member_id: int,
    comment: str | None = None,
    manual_override: bool = False,
) -> dict[str, Any]:
    """Assign a team member (team_member_id) to one final roster slot. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        assignment = upsert_roster_slot_assignment(
            db,
            RosterSlotAssignmentUpsert(
                roster_slot_id=roster_slot_id,
                team_member_id=team_member_id,
                comment=comment,
                manual_override=manual_override,
            ),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(assignment)


@mcp.tool
def clear_roster_slot_assignment_tool(token: str, roster_slot_id: int) -> dict[str, bool]:
    """Clear one final roster slot assignment. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        deleted = clear_roster_slot_assignment(
            db,
            RosterSlotAssignmentClear(roster_slot_id=roster_slot_id),
            organization_id=mcp_organization_id(),
            actor="mcp",
            source="mcp",
        )
        return {"deleted": deleted}


@mcp.tool
def delete_shift_variant_tool(token: str, shift_variant_id: int) -> dict[str, bool]:
    """Delete a shift variant and clear generated slots/assignments for it. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        return {
            "deleted": delete_shift_variant(
                db, shift_variant_id, organization_id=mcp_organization_id(), actor="mcp", source="mcp"
            )
        }


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT")
    if transport == "http":
        mcp.run(
            transport="http",
            host=os.getenv("MCP_HOST", "127.0.0.1"),
            port=int(os.getenv("MCP_PORT", "8001")),
        )
    else:
        mcp.run()
