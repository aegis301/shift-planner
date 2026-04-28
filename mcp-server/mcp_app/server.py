from contextlib import contextmanager
from datetime import date, time
import os
from typing import Any

from fastmcp import FastMCP
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.schemas import (
    AvailabilityRequestCreate,
    DoctorPeriodNoteUpsert,
    DoctorCreate,
    PlanningCellBulkUpsert,
    PlanningCellUpsert,
    PlanningPeriodCreate,
    RosterAssignmentCreate,
    RosterSlotAssignmentClear,
    RosterSlotAssignmentUpsert,
    ShiftTypeCreate,
)
from app.services.doctors import create_doctor, list_doctors
from app.services.matrix import (
    bulk_upsert_planning_cells,
    get_planning_matrix,
    list_doctor_period_notes,
    save_doctor_period_note,
    upsert_planning_cell,
)
from app.services.planning import (
    assign_shift,
    create_planning_period,
    list_planning_periods,
    list_requests,
    list_roster_assignments,
    record_availability_request,
)
from app.services.roster_matrix import (
    clear_roster_slot_assignment,
    get_roster_matrix,
    upsert_roster_slot_assignment,
)
from app.services.shift_types import create_shift_type, list_shift_types
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


@mcp.resource("shift-planner://shift-types")
def shift_types_resource() -> list[dict[str, Any]]:
    """List all shift types."""
    with db_session() as db:
        return [serialize_model(shift_type) for shift_type in list_shift_types(db)]


@mcp.resource("shift-planner://planning-periods")
def planning_periods_resource() -> list[dict[str, Any]]:
    """List monthly planning periods."""
    with db_session() as db:
        return [serialize_model(period) for period in list_planning_periods(db)]


@mcp.resource("shift-planner://requests")
def requests_resource() -> list[dict[str, Any]]:
    """List availability requests."""
    with db_session() as db:
        return [serialize_model(request) for request in list_requests(db)]


@mcp.resource("shift-planner://roster")
def roster_resource() -> list[dict[str, Any]]:
    """List roster assignments."""
    with db_session() as db:
        return [serialize_model(assignment) for assignment in list_roster_assignments(db)]


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
def create_shift_type_tool(
    token: str,
    code: str,
    name_de: str,
    name_en: str,
    starts_at: str,
    ends_at: str,
    category: str = "day",
) -> dict[str, Any]:
    """Create a shift type. Time values must be HH:MM or HH:MM:SS. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        shift_type = create_shift_type(
            db,
            ShiftTypeCreate(
                code=code,
                name_de=name_de,
                name_en=name_en,
                starts_at=time.fromisoformat(starts_at),
                ends_at=time.fromisoformat(ends_at),
                category=category,  # type: ignore[arg-type]
            ),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(shift_type)


@mcp.tool
def create_planning_period_tool(token: str, year: int, month: int) -> dict[str, Any]:
    """Create or return a monthly planning period. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        period = create_planning_period(db, PlanningPeriodCreate(year=year, month=month), actor="mcp", source="mcp")
        return serialize_model(period)


@mcp.tool
def record_availability_request_tool(
    token: str,
    doctor_id: int,
    planning_period_id: int,
    request_date: str,
    request_type: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Record a wish, no-go, or preference. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        request = record_availability_request(
            db,
            AvailabilityRequestCreate(
                doctor_id=doctor_id,
                planning_period_id=planning_period_id,
                request_date=date.fromisoformat(request_date),
                request_type=request_type,  # type: ignore[arg-type]
                note=note,
            ),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(request)


@mcp.tool
def assign_shift_tool(
    token: str,
    doctor_id: int,
    planning_period_id: int,
    shift_type_id: int,
    assignment_date: str,
    note: str | None = None,
    manual_override: bool = False,
) -> dict[str, Any]:
    """Assign a doctor to a shift. Requires MCP admin token."""
    require_token(token)
    with db_session() as db:
        assignment = assign_shift(
            db,
            RosterAssignmentCreate(
                doctor_id=doctor_id,
                planning_period_id=planning_period_id,
                shift_type_id=shift_type_id,
                assignment_date=date.fromisoformat(assignment_date),
                note=note,
                manual_override=manual_override,
            ),
            actor="mcp",
            source="mcp",
        )
        return serialize_model(assignment)


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
