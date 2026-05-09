from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.models import PlanningCell, PlanningShiftIntent, RosterSlotAssignment, RuleConfig
from app.schemas import PLANNED_DUTY_STATUSES, UNAVAILABLE_STATUSES, ValidationWarning
from app.services.constraints import evaluate_assignment_constraints, resolve_slot_constraints
from app.services.matrix import list_planning_cells, list_planning_shift_intents
from app.services.roster_matrix import list_roster_slot_assignments, list_roster_slots
from app.services.shift_groups import active_team_member_ids_in_shift_group, require_shift_group, shift_template_ids_in_shift_group
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
    warning: ValidationWarning, *, team_member_ids: set[int], slot_ids: set[int]
) -> bool:
    if warning.team_member_id is not None and warning.team_member_id not in team_member_ids:
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
    if warning.code.startswith("ROSTER_CONSTRAINT"):
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
    _add_roster_constraint_conflicts(db, warnings, slot_assignments, cells)
    if shift_group_id is None:
        return warnings
    require_shift_group(db, shift_group_id, organization_id)
    team_member_ids = active_team_member_ids_in_shift_group(db, shift_group_id)
    template_ids = shift_template_ids_in_shift_group(db, shift_group_id)
    slot_ids = {
        slot.id
        for slot in list_roster_slots(db, planning_period_id=planning_period_id)
        if slot.shift_template_id is not None and slot.shift_template_id in template_ids
    }
    return [
        warning
        for warning in warnings
        if _warning_in_shift_group_scope(warning, team_member_ids=team_member_ids, slot_ids=slot_ids)
    ]


def _add_matrix_conflicts(warnings: list[ValidationWarning], cells: list[PlanningCell]) -> None:
    duties = [cell for cell in cells if cell.status in PLANNED_DUTY_STATUSES]
    unavailable = {
        (cell.team_member_id, cell.cell_date): cell
        for cell in cells
        if cell.status in UNAVAILABLE_STATUSES
    }
    for duty in duties:
        conflict = unavailable.get((duty.team_member_id, duty.cell_date))
        if conflict:
            warnings.append(
                ValidationWarning(
                    code="MATRIX_UNAVAILABLE_CONFLICT",
                    severity="error",
                    message="Planned duty conflicts with an unavailable matrix status.",
                    team_member_id=duty.team_member_id,
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
        (cell.team_member_id, cell.cell_date): cell
        for cell in cells
        if cell.status in UNAVAILABLE_STATUSES
    }
    for assignment in assignments:
        conflict = unavailable.get((assignment.team_member_id, assignment.roster_slot.slot_date))
        if conflict is None:
            continue
        warnings.append(
            ValidationWarning(
                code="ROSTER_MATRIX_UNAVAILABLE_CONFLICT",
                severity="error",
                message="Final roster assignment conflicts with an unavailable wishes matrix status.",
                team_member_id=assignment.team_member_id,
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
            if intent.team_member_id != assignment.team_member_id:
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
                    team_member_id=assignment.team_member_id,
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
    assignments_by_member_day: dict[tuple[int, date], list[RosterSlotAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_member_day[(assignment.team_member_id, assignment.roster_slot.slot_date)].append(assignment)
    for (team_member_id, assignment_date), day_assignments in assignments_by_member_day.items():
        if len(day_assignments) < 2:
            continue
        warnings.append(
            ValidationWarning(
                code="ROSTER_MATRIX_DUPLICATE_DAY",
                severity="warning",
                message="Team member is assigned to more than one final roster slot on the same day.",
                team_member_id=team_member_id,
                date=assignment_date,
                details={
                    "roster_slot_ids": [assignment.roster_slot_id for assignment in day_assignments],
                    "count": len(day_assignments),
                },
            )
        )


def _add_roster_constraint_conflicts(
    db: Session,
    warnings: list[ValidationWarning],
    assignments: list[RosterSlotAssignment],
    cells: list[PlanningCell],
) -> None:
    assignments_by_member: dict[int, list[RosterSlotAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignments_by_member[assignment.team_member_id].append(assignment)
    cells_by_member: dict[int, list[PlanningCell]] = defaultdict(list)
    for cell in cells:
        cells_by_member[cell.team_member_id].append(cell)
    for assignment in assignments:
        slot = assignment.roster_slot
        if slot is None:
            continue
        resolved = resolve_slot_constraints(db, slot)
        if not resolved:
            continue
        member_assignments = assignments_by_member.get(assignment.team_member_id, [])
        member_cells = cells_by_member.get(assignment.team_member_id, [])
        warnings.extend(
            evaluate_assignment_constraints(
                slot=slot,
                team_member_id=assignment.team_member_id,
                resolved_constraints=resolved,
                assigned_slots_for_member=member_assignments,
                planning_cells_for_member=member_cells,
                assignment_id=assignment.id,
            )
        )
