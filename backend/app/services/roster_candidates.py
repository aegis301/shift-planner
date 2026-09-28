import logging
from time import perf_counter

from sqlalchemy import Integer, cast, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import AuditLog, RosterSlot, ShiftSwapRequest, TeamMember
from app.schemas import (
    SlotCandidateHistoryRead,
    SlotCandidateRead,
    SlotCandidatesRead,
    SlotCandidateSwapRead,
    ValidationWarning,
)
from app.services.constraints import find_blocking_constraint
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group
from app.services.roster_matrix import _team_member_has_template_no_go, _warning_targets_slot
from app.services.rules import build_plan_state, evaluate_plan_state
from app.services.rules.shift_constraints import overlay_candidate_assignment
from app.services.shift_groups import (
    shift_group_ids_for_template,
    team_member_may_cover_template,
)
from app.services.solver.model import eligible_members_for_slots
from app.services.team_members import team_member_planning_display_name
from app.services.tenancy import require_planning_period_in_org
from app.services.unavailable_overlap import find_blocking_unavailable_overlap

logger = logging.getLogger(__name__)


def list_slot_candidates(
    db: Session,
    roster_slot_id: int,
    *,
    organization_id: int,
    shift_group_id: int,
) -> SlotCandidatesRead:
    started = perf_counter()
    slot = db.scalars(
        select(RosterSlot)
        .where(RosterSlot.id == roster_slot_id)
        .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.shift_variant))
    ).first()
    if slot is None:
        raise ValueError("Roster slot not found")
    require_planning_period_in_org(db, slot.planning_period_id, organization_id)
    template_groups = shift_group_ids_for_template(db, slot.shift_template_id) if slot.shift_template_id else set()
    if template_groups and shift_group_id not in template_groups:
        raise ValueError("Shift group does not cover this slot")
    member_ids = sorted(
        team_member_ids_for_period_shift_group(
            db,
            planning_period_id=slot.planning_period_id,
            shift_group_id=shift_group_id,
        )
    )
    members = {
        row.id: row
        for row in db.scalars(select(TeamMember).where(TeamMember.id.in_(member_ids or [-1]))).all()
    }
    state = build_plan_state(
        db,
        organization_id=organization_id,
        start_date=slot.slot_date,
        end_date=slot.slot_date,
    )
    eligible = eligible_members_for_slots(db, state=state, target_slots=[slot]).get(slot.id, set())
    current = state.assignments_by_slot_id.get(slot.id)
    current_member_id = current.team_member_id if current is not None else None
    candidates: list[SlotCandidateRead] = []
    for member_id in member_ids:
        member = members.get(member_id)
        if member is None:
            continue
        overlaid = overlay_candidate_assignment(
            state,
            slot=slot,
            team_member_id=member_id,
            assignment_id=None,
            manual_override=False,
        )
        findings = [
            warning
            for warning in evaluate_plan_state(overlaid, db=db)
            if _warning_targets_slot(warning, slot_id=slot.id, team_member_id=member_id)
        ]
        wish, no_go = _intent_flags(state.shift_intents, member_id=member_id, slot=slot, shift_group_id=shift_group_id)
        day_status = _day_status(state, member_id=member_id, slot=slot, shift_group_id=shift_group_id)
        refused = _assignment_would_refuse(
            db,
            slot=slot,
            team_member_id=member_id,
            findings=findings,
            no_go=no_go,
        )
        if refused:
            status = "blocked"
        elif member_id not in eligible:
            status = "ineligible"
        elif any(warning.severity == "warning" for warning in findings):
            status = "warning"
        else:
            status = "ok"
        candidates.append(
            SlotCandidateRead(
                team_member_id=member_id,
                display_name=team_member_planning_display_name(member),
                status=status,
                findings=findings,
                wish=wish,
                no_go=no_go,
                day_status=day_status,
                fairness_deviation=None,
                is_current_assignee=member_id == current_member_id,
            )
        )
    elapsed = perf_counter() - started
    logger.info(
        "slot candidates slot=%s members=%s seconds=%.3f",
        roster_slot_id,
        len(candidates),
        elapsed,
    )
    template = slot.shift_template
    variant = slot.shift_variant
    return SlotCandidatesRead(
        roster_slot_id=slot.id,
        planning_period_id=slot.planning_period_id,
        shift_group_id=shift_group_id,
        slot_date=slot.slot_date,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        day_class=slot.day_class,
        template_name=template.name if template is not None else None,
        variant_label=variant.label if variant is not None else None,
        category=template.category if template is not None else None,
        candidates=candidates,
        assignment_history=_assignment_history(db, slot.id),
        swap_requests=_swap_requests(db, slot.id),
    )


def _intent_flags(intents, *, member_id: int, slot: RosterSlot, shift_group_id: int) -> tuple[bool, bool]:
    wish = False
    no_go = False
    for intent in intents:
        if intent.team_member_id != member_id or intent.cell_date != slot.slot_date:
            continue
        if intent.shift_group_id != shift_group_id:
            continue
        if slot.shift_template_id is not None and intent.shift_template_id != slot.shift_template_id:
            continue
        if intent.kind == "wish":
            wish = True
        elif intent.kind == "no_go":
            no_go = True
    return wish, no_go


def _day_status(state, *, member_id: int, slot: RosterSlot, shift_group_id: int) -> str | None:
    cell = state.cells_by_member_date_group.get((member_id, slot.slot_date, shift_group_id))
    if cell is None or not cell.status:
        return None
    return cell.status


def _assignment_would_refuse(
    db: Session,
    *,
    slot: RosterSlot,
    team_member_id: int,
    findings: list[ValidationWarning],
    no_go: bool,
) -> bool:
    if not team_member_may_cover_template(db, team_member_id=team_member_id, shift_template_id=slot.shift_template_id):
        return True
    group_ids = shift_group_ids_for_template(db, slot.shift_template_id) if slot.shift_template_id is not None else set()
    if group_ids:
        on_roster = any(
            team_member_id
            in team_member_ids_for_period_shift_group(
                db, planning_period_id=slot.planning_period_id, shift_group_id=group_id
            )
            for group_id in group_ids
        )
        if not on_roster:
            return True
    if no_go or _team_member_has_template_no_go(
        db,
        planning_period_id=slot.planning_period_id,
        team_member_id=team_member_id,
        slot_date=slot.slot_date,
        shift_template_id=slot.shift_template_id,
    ):
        return True
    overlap = next((warning for warning in findings if warning.code == "ROSTER_MATRIX_UNAVAILABLE_OVERLAP"), None)
    if find_blocking_unavailable_overlap(overlap) is not None:
        return True
    return find_blocking_constraint(findings) is not None


def _assignment_history(db: Session, roster_slot_id: int) -> list[SlotCandidateHistoryRead]:
    slot_id = cast(AuditLog.details["roster_slot_id"].as_string(), Integer)
    rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.entity_type == "roster_slot_assignment",
            slot_id == roster_slot_id,
        )
        .order_by(AuditLog.id.desc())
        .limit(400)
    ).all()
    history: list[SlotCandidateHistoryRead] = []
    for row in rows:
        details = row.details or {}
        if details.get("roster_slot_id") != roster_slot_id:
            continue
        history.append(
            SlotCandidateHistoryRead(
                id=row.id,
                action=row.action,
                actor=row.actor,
                created_at=row.created_at,
                team_member_id=details.get("team_member_id"),
            )
        )
    return history


def _swap_requests(db: Session, roster_slot_id: int) -> list[SlotCandidateSwapRead]:
    rows = db.scalars(
        select(ShiftSwapRequest)
        .where(
            or_(
                ShiftSwapRequest.offered_slot_id == roster_slot_id,
                ShiftSwapRequest.counterparty_slot_id == roster_slot_id,
            )
        )
        .order_by(ShiftSwapRequest.id.desc())
    ).all()
    return [
        SlotCandidateSwapRead(
            id=row.id,
            kind=row.kind,
            status=row.status,
            offered_by_team_member_id=row.offered_by_team_member_id,
            target_team_member_id=row.target_team_member_id,
        )
        for row in rows
    ]
