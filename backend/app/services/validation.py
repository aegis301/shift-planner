from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.models import PlanningCell, PlanningShiftIntent, RosterSlotAssignment, RuleConfig
from app.schemas import PLANNED_DUTY_STATUSES, UNAVAILABLE_STATUSES, ValidationWarning
from app.services.matrix import list_planning_cells, list_planning_shift_intents
from app.services.roster_matrix import list_roster_slot_assignments, list_roster_slots
from app.services.shift_groups import active_doctor_ids_in_shift_group, require_shift_group, shift_template_ids_in_shift_group
from app.services.tenancy import require_planning_period_in_org


def get_default_rule_config(db: Session) -> RuleConfig:
    config = db.query(RuleConfig).filter(RuleConfig.name == "default").one_or_none()
    if config:
        return config
    config = RuleConfig(name="default")
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _warning_in_shift_group_scope(
    warning: ValidationWarning, *, doctor_ids: set[int], slot_ids: set[int]
) -> bool:
    if warning.doctor_id is not None and warning.doctor_id not in doctor_ids:
        return False
    if warning.code == "ROSTER_MATRIX_UNAVAILABLE_CONFLICT":
        rid = warning.details.get("roster_slot_id")
        if rid is not None and rid not in slot_ids:
            return False
    if warning.code == "ROSTER_MATRIX_DUPLICATE_DAY":
        ids = warning.details.get("roster_slot_ids") or []
        if ids and not set(ids).issubset(slot_ids):
            return False
    if warning.code == "ROSTER_TEMPLATE_NO_GO_CONFLICT":
        rid = warning.details.get("roster_slot_id")
        if rid is not None and rid not in slot_ids:
            return False
    return True


def validate_roster(
    db: Session, planning_period_id: int, *, organization_id: int, shift_group_id: int | None = None
) -> list[ValidationWarning]:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    warnings: list[ValidationWarning] = []
    cells = list_planning_cells(db, planning_period_id=planning_period_id)
    slot_assignments = list_roster_slot_assignments(db, planning_period_id=planning_period_id)
    intents = list_planning_shift_intents(db, planning_period_id=planning_period_id)
    _add_matrix_conflicts(warnings, cells)
    _add_roster_slot_matrix_conflicts(warnings, slot_assignments, cells)
    _add_roster_template_no_go_conflicts(warnings, slot_assignments, intents)
    _add_roster_slot_duplicate_day_warnings(warnings, slot_assignments)
    if shift_group_id is None:
        return warnings
    require_shift_group(db, shift_group_id, organization_id)
    doctor_ids = active_doctor_ids_in_shift_group(db, shift_group_id)
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    slot_ids = {
        slot.id
        for slot in list_roster_slots(db, planning_period_id=planning_period_id)
        if slot.shift_template_id is not None and slot.shift_template_id in template_ids
    }
    return [warning for warning in warnings if _warning_in_shift_group_scope(warning, doctor_ids=doctor_ids, slot_ids=slot_ids)]


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
                    "shift_template_id": assignment.roster_slot.shift_template_id,
                    "shift_variant_id": assignment.roster_slot.shift_variant_id,
                    "unavailable_status": conflict.status,
                },
            )
        )


def _add_roster_template_no_go_conflicts(
    warnings: list[ValidationWarning],
    assignments: list[RosterSlotAssignment],
    intents: list[PlanningShiftIntent],
) -> None:
    no_gos = [intent for intent in intents if intent.kind == "no_go"]
    for assignment in assignments:
        if assignment.manual_override:
            continue
        slot = assignment.roster_slot
        template_id = slot.shift_template_id
        if template_id is None:
            continue
        for intent in no_gos:
            if intent.doctor_id != assignment.doctor_id:
                continue
            if intent.cell_date != slot.slot_date:
                continue
            if intent.shift_template_id != template_id:
                continue
            warnings.append(
                ValidationWarning(
                    code="ROSTER_TEMPLATE_NO_GO_CONFLICT",
                    severity="error",
                    message="Final roster assignment conflicts with a shift no-go.",
                    doctor_id=assignment.doctor_id,
                    date=slot.slot_date,
                    details={
                        "roster_slot_id": assignment.roster_slot_id,
                        "roster_slot_assignment_id": assignment.id,
                        "shift_template_id": template_id,
                        "shift_variant_id": slot.shift_variant_id,
                        "shift_group_id": intent.shift_group_id,
                    },
                )
            )
            break


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
