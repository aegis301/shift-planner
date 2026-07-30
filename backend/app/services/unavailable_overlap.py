from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.models import PlanningCell, RosterSlot
from app.schemas import ShiftConstraint, ValidationWarning
from app.services.constraints import ResolvedConstraint, resolve_slot_constraints
from app.services.planning_day_status_definitions import cell_status_blocks_roster_assignment
from app.services.shift_intervals import overlap_calendar_days

UnavailableOverlapMode = Literal["allow", "warn", "block"]
UnavailableOverlapSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class ResolvedUnavailableOverlapPolicy:
    mode: UnavailableOverlapMode
    severity: UnavailableOverlapSeverity


def _severity_to_mode(severity: str) -> UnavailableOverlapMode:
    if severity == "error":
        return "block"
    if severity == "warning":
        return "warn"
    return "allow"


def resolve_unavailable_overlap_policy(resolved_constraints: list[ResolvedConstraint]) -> ResolvedUnavailableOverlapPolicy:
    for resolved in resolved_constraints:
        if resolved.rule.type == "unavailable_overlap_policy":
            mode = resolved.rule.unavailable_overlap_mode or "inherit"
            if mode == "inherit":
                continue
            if mode == "allow":
                return ResolvedUnavailableOverlapPolicy(mode="allow", severity="info")
            if mode == "warn":
                return ResolvedUnavailableOverlapPolicy(mode="warn", severity="warning")
            return ResolvedUnavailableOverlapPolicy(mode="block", severity="error")
    for resolved in resolved_constraints:
        if resolved.rule.type == "no_cross_day_into_unavailable_day":
            mode = _severity_to_mode(resolved.rule.severity)
            if mode == "block":
                return ResolvedUnavailableOverlapPolicy(mode="block", severity="error")
            if mode == "warn":
                return ResolvedUnavailableOverlapPolicy(mode="warn", severity="warning")
            return ResolvedUnavailableOverlapPolicy(mode="allow", severity="info")
    return ResolvedUnavailableOverlapPolicy(mode="block", severity="error")


def _blocking_cells_by_date(
    db: Session,
    *,
    planning_cells: list[PlanningCell],
    organization_id: int,
) -> dict[date, PlanningCell]:
    out: dict[date, PlanningCell] = {}
    for cell in planning_cells:
        if cell_status_blocks_roster_assignment(db, organization_id=organization_id, status=cell.status):
            existing = out.get(cell.cell_date)
            if existing is None or cell.id > existing.id:
                out[cell.cell_date] = cell
    return out


def evaluate_unavailable_overlap(
    *,
    db: Session,
    slot: RosterSlot,
    team_member_id: int,
    planning_cells: list[PlanningCell],
    organization_id: int,
    policy: ResolvedUnavailableOverlapPolicy,
    assignment_id: int | None = None,
) -> ValidationWarning | None:
    if policy.mode == "allow":
        return None
    blocking_by_date = _blocking_cells_by_date(db, planning_cells=planning_cells, organization_id=organization_id)
    overlap_days = overlap_calendar_days(db, slot)
    conflicts: list[dict[str, object]] = []
    for day in overlap_days:
        cell = blocking_by_date.get(day)
        if cell is None:
            continue
        conflicts.append(
            {
                "cell_date": day.isoformat(),
                "unavailable_status": cell.status,
            }
        )
    if not conflicts:
        return None
    severity = policy.severity if policy.mode == "block" else "warning"
    first_day = date.fromisoformat(str(conflicts[0]["cell_date"]))
    details: dict[str, object] = {
        "roster_slot_id": slot.id,
        "shift_template_id": slot.shift_template_id,
        "shift_variant_id": slot.shift_variant_id,
        "overlap_days": [row["cell_date"] for row in conflicts],
        "conflicts": conflicts,
        "unavailable_overlap_policy": policy.mode,
        "unavailable_status": conflicts[0]["unavailable_status"],
    }
    if assignment_id is not None:
        details["roster_slot_assignment_id"] = assignment_id
    return ValidationWarning(
        code="ROSTER_MATRIX_UNAVAILABLE_OVERLAP",
        severity=severity,
        message="Final roster assignment overlaps an unavailable wishes matrix status.",
        team_member_id=team_member_id,
        date=first_day,
        details=details,
    )


def evaluate_unavailable_overlap_for_slot(
    *,
    db: Session,
    slot: RosterSlot,
    team_member_id: int,
    planning_cells: list[PlanningCell],
    organization_id: int,
    assignment_id: int | None = None,
) -> ValidationWarning | None:
    resolved = resolve_slot_constraints(db, slot)
    policy = resolve_unavailable_overlap_policy(resolved)
    return evaluate_unavailable_overlap(
        db=db,
        slot=slot,
        team_member_id=team_member_id,
        planning_cells=planning_cells,
        organization_id=organization_id,
        policy=policy,
        assignment_id=assignment_id,
    )


def find_blocking_unavailable_overlap(warning: ValidationWarning | None) -> ValidationWarning | None:
    if warning is None:
        return None
    if warning.severity == "error":
        return warning
    return None
