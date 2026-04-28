from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.models import AvailabilityRequest, PlanningCell, RosterAssignment, RosterSlotAssignment, RuleConfig, ShiftType
from app.schemas import PLANNED_DUTY_STATUSES, UNAVAILABLE_STATUSES, ValidationWarning
from app.services.matrix import list_planning_cells
from app.services.planning import list_requests, list_roster_assignments
from app.services.roster_matrix import list_roster_slot_assignments


def get_default_rule_config(db: Session) -> RuleConfig:
    config = db.query(RuleConfig).filter(RuleConfig.name == "default").one_or_none()
    if config:
        return config
    config = RuleConfig(name="default")
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def validate_roster(db: Session, planning_period_id: int) -> list[ValidationWarning]:
    config = get_default_rule_config(db)
    assignments = list_roster_assignments(db, planning_period_id=planning_period_id)
    requests = list_requests(db, planning_period_id=planning_period_id)
    warnings: list[ValidationWarning] = []
    cells = list_planning_cells(db, planning_period_id=planning_period_id)
    slot_assignments = list_roster_slot_assignments(db, planning_period_id=planning_period_id)
    _add_matrix_conflicts(warnings, cells)
    _add_roster_slot_matrix_conflicts(warnings, slot_assignments, cells)
    _add_roster_slot_duplicate_day_warnings(warnings, slot_assignments)
    _add_matrix_legacy_request_conflicts(warnings, cells, requests)
    _add_no_go_conflicts(warnings, assignments, requests)
    _add_night_load_warnings(warnings, assignments, config)
    return warnings


def _add_matrix_conflicts(warnings: list[ValidationWarning], cells: list[PlanningCell]) -> None:
    duties = [cell for cell in cells if cell.status in PLANNED_DUTY_STATUSES]
    unavailable = {
        (cell.doctor_id, cell.cell_date): cell
        for cell in cells
        if cell.status in UNAVAILABLE_STATUSES
    }
    for duty in duties:
        conflict = unavailable.get((duty.doctor_id, duty.cell_date))
        if conflict:
            warnings.append(
                ValidationWarning(
                    code="MATRIX_UNAVAILABLE_CONFLICT",
                    severity="error",
                    message="Planned duty conflicts with an unavailable matrix status.",
                    doctor_id=duty.doctor_id,
                    date=duty.cell_date,
                    details={"duty_status": duty.status, "unavailable_status": conflict.status},
                )
            )


def _add_roster_slot_matrix_conflicts(
    warnings: list[ValidationWarning],
    assignments: list[RosterSlotAssignment],
    cells: list[PlanningCell],
) -> None:
    unavailable = {
        (cell.doctor_id, cell.cell_date): cell
        for cell in cells
        if cell.status in UNAVAILABLE_STATUSES
    }
    for assignment in assignments:
        conflict = unavailable.get((assignment.doctor_id, assignment.roster_slot.slot_date))
        if conflict is None:
            continue
        warnings.append(
            ValidationWarning(
                code="ROSTER_MATRIX_UNAVAILABLE_CONFLICT",
                severity="error",
                message="Final roster assignment conflicts with an unavailable wishes matrix status.",
                doctor_id=assignment.doctor_id,
                date=assignment.roster_slot.slot_date,
                details={
                    "roster_slot_id": assignment.roster_slot_id,
                    "roster_slot_assignment_id": assignment.id,
                    "shift_type_id": assignment.roster_slot.shift_type_id,
                    "unavailable_status": conflict.status,
                },
            )
        )


def _add_roster_slot_duplicate_day_warnings(
    warnings: list[ValidationWarning],
    assignments: list[RosterSlotAssignment],
) -> None:
    assignments_by_doctor_day: dict[tuple[int, date], list[RosterSlotAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_doctor_day[(assignment.doctor_id, assignment.roster_slot.slot_date)].append(assignment)
    for (doctor_id, assignment_date), day_assignments in assignments_by_doctor_day.items():
        if len(day_assignments) < 2:
            continue
        warnings.append(
            ValidationWarning(
                code="ROSTER_MATRIX_DUPLICATE_DAY",
                severity="warning",
                message="Doctor is assigned to more than one final roster slot on the same day.",
                doctor_id=doctor_id,
                date=assignment_date,
                details={
                    "roster_slot_ids": [assignment.roster_slot_id for assignment in day_assignments],
                    "count": len(day_assignments),
                },
            )
        )


def _add_matrix_legacy_request_conflicts(
    warnings: list[ValidationWarning],
    cells: list[PlanningCell],
    requests: list[AvailabilityRequest],
) -> None:
    no_gos = {(request.doctor_id, request.request_date): request for request in requests if request.request_type == "no_go"}
    for cell in cells:
        if cell.status not in PLANNED_DUTY_STATUSES:
            continue
        request = no_gos.get((cell.doctor_id, cell.cell_date))
        if request:
            warnings.append(
                ValidationWarning(
                    code="MATRIX_LEGACY_NO_GO_CONFLICT",
                    severity="error",
                    message="Matrix duty conflicts with a legacy no-go request.",
                    doctor_id=cell.doctor_id,
                    request_id=request.id,
                    date=cell.cell_date,
                    details={"status": cell.status},
                )
            )


def _add_no_go_conflicts(
    warnings: list[ValidationWarning],
    assignments: list[RosterAssignment],
    requests: list[AvailabilityRequest],
) -> None:
    no_gos = {(request.doctor_id, request.request_date): request for request in requests if request.request_type == "no_go"}
    for assignment in assignments:
        request = no_gos.get((assignment.doctor_id, assignment.assignment_date))
        if request:
            warnings.append(
                ValidationWarning(
                    code="NO_GO_CONFLICT",
                    severity="error",
                    message="Assignment conflicts with a no-go request.",
                    doctor_id=assignment.doctor_id,
                    assignment_id=assignment.id,
                    request_id=request.id,
                    date=assignment.assignment_date,
                )
            )


def _add_night_load_warnings(
    warnings: list[ValidationWarning],
    assignments: list[RosterAssignment],
    config: RuleConfig,
) -> None:
    nights_by_doctor: dict[int, int] = defaultdict(int)
    for assignment in assignments:
        shift_type = assignment.shift_type
        if isinstance(shift_type, ShiftType) and shift_type.category == "night":
            nights_by_doctor[assignment.doctor_id] += 1
    for doctor_id, count in nights_by_doctor.items():
        if count > config.max_monthly_nights_full_time:
            warnings.append(
                ValidationWarning(
                    code="NIGHT_LOAD",
                    severity="warning",
                    message="Doctor exceeds configured monthly night shift warning threshold.",
                    doctor_id=doctor_id,
                    details={"count": count, "limit": config.max_monthly_nights_full_time},
                )
            )
