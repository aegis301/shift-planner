from contextlib import contextmanager
from datetime import date, time
import os
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas import (
    DoctorPeriodNoteUpsert,
    DoctorCreate,
    PlanningCellBulkUpsert,
    PlanningCellUpsert,
    PlanningPeriodCreate,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentUpsert,
    ShiftTemplateCreate,
    ShiftVariantCreate,
)
from app.services.doctors import create_doctor, delete_doctor, list_doctors
from app.services.matrix import (
    bulk_upsert_planning_cells,
    get_planning_matrix,
    list_doctor_period_notes,
    save_doctor_period_note,
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
from app.services.shift_templates import (
    create_shift_template,
    create_shift_variant,
    delete_shift_template,
    delete_shift_variant,
    list_shift_templates,
    preview_slots_for_month,
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


@mcp.resource("shift-planner://doctors")
def doctors_resource() -> list[dict[str, Any]]:
    """List all doctors."""
    with db_session() as db:
        return [serialize_model(doctor) for doctor in list_doctors(db)]


@mcp.resource("shift-planner://shift-templates")
def shift_templates_resource() -> list[dict[str, Any]]:
    """List all shift templates with variant metadata."""
    with db_session() as db:
        return [
            {
                **serialize_model(template),
                "variants": [serialize_model(variant) for variant in template.variants],
            }
            for template in list_shift_templates(db)
        ]


@mcp.resource("shift-planner://planning-periods")
def planning_periods_resource() -> list[dict[str, Any]]:
    """List monthly planning periods."""
    with db_session() as db:
        return [serialize_model(period) for period in list_planning_periods(db)]


@mcp.resource("shift-planner://matrix/{planning_period_id}")
def matrix_resource(planning_period_id: int) -> dict[str, Any]:
    """Return the monthly planning matrix with days, doctors, and cells."""
    with db_session() as db:
        return get_planning_matrix(db, planning_period_id).model_dump(mode="json")


@mcp.resource("shift-planner://roster-matrix/{planning_period_id}")
def roster_matrix_resource(planning_period_id: int) -> dict[str, Any]:
    """Return the final roster matrix with days, shift slots, doctors, and assignments."""
    with db_session() as db:
        return get_roster_matrix(db, planning_period_id).model_dump(mode="json")


@mcp.resource("shift-planner://doctor-period-notes/{planning_period_id}")
def doctor_period_notes_resource(planning_period_id: int) -> list[dict[str, Any]]:
    """Return source emails and monthly notes for a planning period."""
    with db_session() as db:
        return [serialize_model(note) for note in list_doctor_period_notes(db, planning_period_id=planning_period_id)]


@mcp.tool
def get_validation_warnings(planning_period_id: int) -> list[dict[str, Any]]:
    """Validate a planning period and return structured warnings."""
    with db_session() as db:
        return [warning.model_dump(mode="json") for warning in validate_roster(db, planning_period_id)]


@mcp.tool
def create_doctor_tool(
    token: str,
    name: str,
    email: str,
    employment_percentage: int = 100,
    notes: str | None = None,
) -> dict[str, Any]:
    """Create a doctor. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        doctor = create_doctor(
            db,
            DoctorCreate(name=name, email=email, employment_percentage=employment_percentage, notes=notes),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(doctor)


@mcp.tool
def delete_doctor_tool(token: str, doctor_id: int) -> dict[str, bool]:
    """Delete a doctor and clear related wishes/notes/assignments. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        return {"deleted": delete_doctor(db, doctor_id, actor="mcp", source="mcp")}


@mcp.tool
def create_shift_template_tool(
    token: str,
    code: str,
    name_de: str,
    name_en: str,
    category: str = "bereitschaftsdienst",
    display_order: int = 0,
) -> dict[str, Any]:
    """Create a shift template. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        template = create_shift_template(
            db,
            ShiftTemplateCreate(
                code=code,
                name_de=name_de,
                name_en=name_en,
                category=category,  # type: ignore[arg-type]
                display_order=display_order,
            ),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(template)


@mcp.tool
def delete_shift_template_tool(token: str, shift_template_id: int) -> dict[str, bool]:
    """Delete a shift template, its variants, generated slots, and assignments. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        return {"deleted": delete_shift_template(db, shift_template_id, actor="mcp", source="mcp")}


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
            ),
            actor="mcp",
            source="mcp",
        )
        if variant is None:
            raise ValueError("Shift template not found")
        return serialize_model(variant)


@mcp.tool
def preview_shift_slots_tool(year: int, month: int) -> list[dict[str, Any]]:
    """Preview generated concrete roster slots for a month."""
    with db_session() as db:
        return [slot.model_dump(mode="json") for slot in preview_slots_for_month(db, year=year, month=month)]


@mcp.tool
def create_planning_period_tool(token: str, year: int, month: int) -> dict[str, Any]:
    """Create or return a monthly planning period. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        period = create_planning_period(db, PlanningPeriodCreate(year=year, month=month), actor="mcp", source="mcp")
        return serialize_model(period)


@mcp.tool
def regenerate_planning_period_roster_tool(token: str, planning_period_id: int) -> dict[str, Any]:
    """Delete roster slots and assignments for a period, then regenerate slots from current templates."""
    require_token(token)
    with db_session() as db:
        reset_roster_slots_for_period(db, planning_period_id, actor="mcp", source="mcp")
        return get_roster_matrix(db, planning_period_id).model_dump(mode="json")


@mcp.tool
def delete_planning_period_tool(token: str, planning_period_id: int) -> dict[str, bool]:
    """Delete a planning period and all related wishes, notes, roster slots, and assignments."""
    require_token(token)
    with db_session() as db:
        return {"deleted": delete_planning_period(db, planning_period_id, actor="mcp", source="mcp")}


@mcp.tool
def upsert_planning_cell_tool(
    token: str,
    planning_period_id: int,
    doctor_id: int,
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
                doctor_id=doctor_id,
                cell_date=date.fromisoformat(cell_date),
                status=status,  # type: ignore[arg-type]
                comment=comment,
            ),
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
                doctor_id=int(cell["doctor_id"]),
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
            for cell in bulk_upsert_planning_cells(db, planning_period_id, payload, actor="mcp", source="mcp")
        ]


@mcp.tool
def save_doctor_period_note_tool(
    token: str,
    planning_period_id: int,
    doctor_id: int,
    source_text: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Save a doctor's monthly source email/general note. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        note = save_doctor_period_note(
            db,
            planning_period_id,
            DoctorPeriodNoteUpsert(doctor_id=doctor_id, source_text=source_text, summary=summary),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(note)


@mcp.tool
def upsert_roster_slot_assignment_tool(
    token: str,
    roster_slot_id: int,
    doctor_id: int,
    comment: str | None = None,
    manual_override: bool = False,
) -> dict[str, Any]:
    """Assign a doctor to one final roster slot. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        assignment = upsert_roster_slot_assignment(
            db,
            RosterSlotAssignmentUpsert(
                roster_slot_id=roster_slot_id,
                doctor_id=doctor_id,
                comment=comment,
                manual_override=manual_override,
            ),
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
            actor="mcp",
            source="mcp",
        )
        return {"deleted": deleted}


@mcp.tool
def delete_shift_variant_tool(token: str, shift_variant_id: int) -> dict[str, bool]:
    """Delete a shift variant and clear generated slots/assignments for it. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        return {"deleted": delete_shift_variant(db, shift_variant_id, actor="mcp", source="mcp")}


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
