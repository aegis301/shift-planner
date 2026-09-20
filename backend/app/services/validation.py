from calendar import monthrange
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.models import PlanningCell, PlanningPeriod
from app.schemas import PLANNED_DUTY_STATUSES, ValidationWarning
from app.services.matrix import list_planning_cells
from app.services.planning_day_status_definitions import cell_status_blocks_roster_assignment
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group
from app.services.roster_matrix import list_roster_slots
from app.services.rules import build_plan_state, evaluate_plan_state
from app.services.shift_groups import require_shift_group, shift_template_ids_in_shift_group
from app.services.tenancy import require_planning_period_in_org


def _warning_in_shift_group_scope(
    warning: ValidationWarning, *, team_member_ids: set[int], slot_ids: set[int]
) -> bool:
    if warning.team_member_id is not None and warning.team_member_id not in team_member_ids:
        return False
    if warning.code == "ROSTER_MATRIX_UNAVAILABLE_OVERLAP":
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
    if warning.code == "ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH":
        vids = warning.details.get("violating_roster_slot_ids")
        if isinstance(vids, list) and vids:
            ids_int = [x for x in vids if isinstance(x, int)]
            return not ids_int or bool(set(ids_int) & slot_ids)
    if warning.code == "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED":
        sids = warning.details.get("source_roster_slot_ids")
        if isinstance(sids, list) and sids:
            ids_int = [x for x in sids if isinstance(x, int)]
            return not ids_int or bool(set(ids_int) & slot_ids)
    if warning.code == "ROSTER_CONSECUTIVE_WEEKENDS":
        ids = warning.details.get("roster_slot_ids")
        if isinstance(ids, list) and ids:
            ids_int = [x for x in ids if isinstance(x, int)]
            if ids_int and not set(ids_int) & slot_ids:
                return False
        return True
    if warning.code.startswith("ROSTER_CONSTRAINT"):
        rid = warning.details.get("roster_slot_id")
        if rid is not None and rid not in slot_ids:
            return False
    if warning.code.startswith("MEMBER_PATTERN"):
        rid = warning.details.get("roster_slot_id")
        if rid is not None and rid not in slot_ids:
            return False
    return True


def _merge_max_assignments_per_month_warnings(warnings: list[ValidationWarning]) -> list[ValidationWarning]:
    non_max: list[ValidationWarning] = []
    max_bucket: dict[tuple[int | None, object, int, str], ValidationWarning] = {}
    slot_ids_by_bucket: dict[tuple[int | None, object, int, str], set[int]] = defaultdict(set)
    for w in warnings:
        if w.code != "ROSTER_CONSTRAINT_MAX_ASSIGNMENTS_PER_MONTH":
            non_max.append(w)
            continue
        cap = w.details.get("max_assignments_per_month")
        if not isinstance(cap, int):
            non_max.append(w)
            continue
        key = (w.team_member_id, w.details.get("shift_template_id"), cap, w.severity)
        rid = w.details.get("roster_slot_id")
        if isinstance(rid, int):
            slot_ids_by_bucket[key].add(rid)
        if key not in max_bucket:
            max_bucket[key] = w
    merged_max: list[ValidationWarning] = []
    for key, w in max_bucket.items():
        slots = sorted(slot_ids_by_bucket.get(key, set()))
        new_details: dict[str, object] = {**w.details}
        new_details.pop("roster_slot_id", None)
        new_details.pop("roster_slot_assignment_id", None)
        if slots:
            new_details["violating_roster_slot_ids"] = slots
        merged_max.append(
            ValidationWarning(
                code=w.code,
                severity=w.severity,
                message="Team member exceeds the maximum monthly assignments allowed for this shift template.",
                team_member_id=w.team_member_id,
                date=None,
                details=new_details,
            )
        )
    return non_max + merged_max


def _merge_coupled_shift_warnings(warnings: list[ValidationWarning]) -> list[ValidationWarning]:
    non_coupled: list[ValidationWarning] = []
    bucket: dict[tuple[int | None, object, object, object, str], ValidationWarning] = {}
    source_ids_by_bucket: dict[tuple[int | None, object, object, object, str], set[int]] = defaultdict(set)
    for w in warnings:
        if w.code != "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED":
            non_coupled.append(w)
            continue
        key = (
            w.team_member_id,
            w.details.get("shift_variant_id"),
            w.details.get("paired_shift_variant_id"),
            w.details.get("partner_date"),
            w.severity,
        )
        rid = w.details.get("roster_slot_id")
        if isinstance(rid, int):
            source_ids_by_bucket[key].add(rid)
        if key not in bucket:
            bucket[key] = w
    merged_coupled: list[ValidationWarning] = []
    for key, w in bucket.items():
        srcs = sorted(source_ids_by_bucket.get(key, set()))
        new_details: dict[str, object] = {**w.details}
        new_details.pop("roster_slot_id", None)
        new_details.pop("roster_slot_assignment_id", None)
        if srcs:
            new_details["source_roster_slot_ids"] = srcs
        merged_coupled.append(
            ValidationWarning(
                code=w.code,
                severity=w.severity,
                message="Constraint violation: required coupled shift assignment is missing.",
                team_member_id=w.team_member_id,
                date=None,
                details=new_details,
            )
        )
    return non_coupled + merged_coupled


def _plan_state_for_period(db: Session, period: PlanningPeriod, *, organization_id: int):
    start_date = date(period.year, period.month, 1)
    end_date = date(period.year, period.month, monthrange(period.year, period.month)[1])
    return build_plan_state(
        db,
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
    )


def validate_roster(
    db: Session, planning_period_id: int, *, organization_id: int, shift_group_id: int | None = None
) -> list[ValidationWarning]:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    warnings: list[ValidationWarning] = []
    cells = list_planning_cells(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    plan_state = _plan_state_for_period(db, period, organization_id=organization_id)
    _add_matrix_conflicts(db, warnings, cells, organization_id=organization_id)
    warnings.extend(evaluate_plan_state(plan_state, db=db))
    warnings = _merge_coupled_shift_warnings(_merge_max_assignments_per_month_warnings(warnings))
    return filter_warnings_for_shift_group(
        db,
        warnings,
        planning_period_id=planning_period_id,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
    )


def filter_warnings_for_shift_group(
    db: Session,
    warnings: list[ValidationWarning],
    *,
    planning_period_id: int,
    organization_id: int,
    shift_group_id: int | None,
) -> list[ValidationWarning]:
    if shift_group_id is None:
        return warnings
    require_shift_group(db, shift_group_id, organization_id)
    team_member_ids = team_member_ids_for_period_shift_group(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
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


def _add_matrix_conflicts(
    db: Session, warnings: list[ValidationWarning], cells: list[PlanningCell], *, organization_id: int
) -> None:
    duties = [cell for cell in cells if cell.status in PLANNED_DUTY_STATUSES]
    unavailable = {
        (cell.team_member_id, cell.cell_date): cell
        for cell in cells
        if cell_status_blocks_roster_assignment(db, organization_id=organization_id, status=cell.status)
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
