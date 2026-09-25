from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import NamedTuple

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.models import (
    PlanningPeriodShiftGroupMember,
    PlanningPlanVersion,
    RosterSlot,
    RosterSlotAssignment,
    ShiftSwapRequest,
    TeamMember,
)
from app.schemas import (
    FairnessAccountsRead,
    FairnessDimension,
    PlanVersionRead,
    RosterSlotAssignmentRead,
    RosterSlotAssignmentUpsert,
    ShiftSwapApplyRead,
    ShiftSwapRequestCreate,
    ShiftSwapRequestRead,
    ShiftSwapUnresolvedRead,
    ValidationWarning,
)
from app.services.audit import record_audit
from app.services.fairness import build_fairness_accounts
from app.services.holidays import classify_day
from app.services.plan_versions import snapshot_swap_apply_plan_version
from app.services.planning import (
    PLANNING_PERIOD_STATUS_PRELIMINARY,
    PLANNING_PERIOD_STATUS_PUBLISHED,
    get_shift_group_planning_status,
)
from app.services.roster_matrix import upsert_roster_slot_assignment
from app.services.rules.builder import NIGHT_AFTER_HOUR, build_plan_state
from app.services.rules.registry import evaluate_plan_state
from app.services.rules.shift_constraints import overlay_candidate_assignment
from app.services.rules.state import PlanState
from app.services.shift_groups import require_shift_group, shift_group_ids_for_template
from app.services.tenancy import require_planning_period_in_org
from app.services.time_entries import refresh_derived_window

SWAP_KIND_GIVEAWAY = "giveaway"
SWAP_KIND_DIRECT = "direct"

SWAP_STATUS_DRAFT = "draft"
SWAP_STATUS_OPEN = "open"
SWAP_STATUS_CLAIMED = "claimed"
SWAP_STATUS_TARGETED = "targeted"
SWAP_STATUS_ACCEPTED = "accepted"
SWAP_STATUS_APPROVED = "approved"
SWAP_STATUS_APPLIED = "applied"
SWAP_STATUS_WITHDRAWN = "withdrawn"
SWAP_STATUS_REJECTED = "rejected"
SWAP_STATUS_EXPIRED = "expired"

ACTIVE_STATUSES = frozenset(
    {
        SWAP_STATUS_DRAFT,
        SWAP_STATUS_OPEN,
        SWAP_STATUS_CLAIMED,
        SWAP_STATUS_TARGETED,
        SWAP_STATUS_ACCEPTED,
        SWAP_STATUS_APPROVED,
    }
)

UNRESOLVED_STATUSES = frozenset({SWAP_STATUS_OPEN, SWAP_STATUS_TARGETED})
APPROVAL_QUEUE_STATUSES = frozenset({SWAP_STATUS_CLAIMED, SWAP_STATUS_ACCEPTED, SWAP_STATUS_APPROVED})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    SWAP_STATUS_DRAFT: frozenset({SWAP_STATUS_OPEN, SWAP_STATUS_TARGETED, SWAP_STATUS_WITHDRAWN}),
    SWAP_STATUS_OPEN: frozenset(
        {SWAP_STATUS_CLAIMED, SWAP_STATUS_TARGETED, SWAP_STATUS_WITHDRAWN, SWAP_STATUS_REJECTED, SWAP_STATUS_EXPIRED}
    ),
    SWAP_STATUS_CLAIMED: frozenset(
        {SWAP_STATUS_APPROVED, SWAP_STATUS_WITHDRAWN, SWAP_STATUS_REJECTED, SWAP_STATUS_EXPIRED}
    ),
    SWAP_STATUS_TARGETED: frozenset(
        {SWAP_STATUS_ACCEPTED, SWAP_STATUS_WITHDRAWN, SWAP_STATUS_REJECTED, SWAP_STATUS_EXPIRED}
    ),
    SWAP_STATUS_ACCEPTED: frozenset(
        {SWAP_STATUS_APPROVED, SWAP_STATUS_WITHDRAWN, SWAP_STATUS_REJECTED, SWAP_STATUS_EXPIRED}
    ),
    SWAP_STATUS_APPROVED: frozenset({SWAP_STATUS_APPLIED, SWAP_STATUS_REJECTED, SWAP_STATUS_EXPIRED}),
    SWAP_STATUS_APPLIED: frozenset(),
    SWAP_STATUS_WITHDRAWN: frozenset(),
    SWAP_STATUS_REJECTED: frozenset(),
    SWAP_STATUS_EXPIRED: frozenset(),
}

SWAP_ASSIGNMENT_SOURCE = "shift_swap"


class ShiftSwapNotFoundError(Exception):
    pass


class ShiftSwapConflictError(Exception):
    def __init__(self, code: str, message: str, findings: list[ValidationWarning] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.findings = findings or []


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _as_utc_date(value: datetime) -> date:
    if value.tzinfo is None:
        return value.date()
    return value.astimezone(UTC).date()


def _dump_findings(findings: list[ValidationWarning]) -> list[dict]:
    return [row.model_dump(mode="json") for row in findings]


def shift_swap_to_read(
    row: ShiftSwapRequest,
    *,
    eligible_member_ids: list[int] | None = None,
) -> ShiftSwapRequestRead:
    payload = ShiftSwapRequestRead.model_validate(row)
    if eligible_member_ids is not None:
        return payload.model_copy(update={"eligible_member_ids": eligible_member_ids})
    return payload


def _require_visible_group_status(
    db: Session,
    *,
    planning_period_id: int,
    shift_group_id: int,
    organization_id: int,
) -> None:
    require_shift_group(db, shift_group_id, organization_id)
    row = get_shift_group_planning_status(
        db,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        organization_id=organization_id,
    )
    if row is None or row.status not in (PLANNING_PERIOD_STATUS_PRELIMINARY, PLANNING_PERIOD_STATUS_PUBLISHED):
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_NOT_VISIBLE",
            "Swaps are only available when the shift group's plan is preliminary or published",
        )


def _load_slot(db: Session, slot_id: int, *, organization_id: int) -> RosterSlot:
    slot = db.get(RosterSlot, slot_id)
    if slot is None:
        raise ValueError("Roster slot not found")
    require_planning_period_in_org(db, slot.planning_period_id, organization_id)
    return slot


def _assignment_for_slot(db: Session, slot_id: int) -> RosterSlotAssignment | None:
    return db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot_id))


def _assert_slot_in_group(db: Session, slot: RosterSlot, shift_group_id: int) -> None:
    if slot.shift_template_id is None:
        return
    group_ids = shift_group_ids_for_template(db, slot.shift_template_id)
    if group_ids and shift_group_id not in group_ids:
        raise ValueError("Roster slot is not in this shift group")


def _assert_transition(row: ShiftSwapRequest, target: str) -> None:
    allowed = ALLOWED_TRANSITIONS.get(row.status, frozenset())
    if target not in allowed:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_INVALID_TRANSITION",
            f"Cannot transition from {row.status} to {target}",
        )


def _active_request_for_slot(db: Session, *, offered_slot_id: int, exclude_id: int | None = None) -> ShiftSwapRequest | None:
    stmt = select(ShiftSwapRequest).where(
        ShiftSwapRequest.offered_slot_id == offered_slot_id,
        ShiftSwapRequest.status.in_(ACTIVE_STATUSES),
    )
    if exclude_id is not None:
        stmt = stmt.where(ShiftSwapRequest.id != exclude_id)
    return db.scalar(stmt)


def _expire_if_past(db: Session, row: ShiftSwapRequest, offered_slot: RosterSlot) -> None:
    if row.status not in ACTIVE_STATUSES or row.status == SWAP_STATUS_APPROVED:
        return
    if offered_slot.slot_date >= _utc_today():
        return
    if SWAP_STATUS_EXPIRED not in ALLOWED_TRANSITIONS.get(row.status, frozenset()):
        return
    row.status = SWAP_STATUS_EXPIRED
    db.commit()
    raise ShiftSwapConflictError("SHIFT_SWAP_EXPIRED", "This swap request has expired")


def _finding_involves_swap(
    warning: ValidationWarning,
    *,
    member_ids: set[int],
    slot_ids: set[int],
) -> bool:
    if warning.team_member_id in member_ids:
        return True
    details = warning.details or {}
    if details.get("roster_slot_id") in slot_ids:
        return True
    if details.get("related_roster_slot_id") in slot_ids:
        return True
    for key in (
        "conflicting_roster_slot_ids",
        "violating_roster_slot_ids",
        "source_roster_slot_ids",
        "roster_slot_ids",
    ):
        ids = details.get(key)
        if isinstance(ids, list) and any(slot_id in slot_ids for slot_id in ids):
            return True
    return False


def _incoming_member_id(row: ShiftSwapRequest) -> int | None:
    return row.target_team_member_id


class _SwapStates(NamedTuple):
    """Two views of one window. ``group`` scopes assignments to the swap's shift group;
    ``person`` adds every duty the in-scope members hold in other groups."""

    group: PlanState
    person: PlanState


def _swap_findings(
    db: Session,
    states: _SwapStates,
    *,
    moves: list[tuple[RosterSlot, int]],
    member_ids: set[int],
) -> tuple[list[ValidationWarning], list[ValidationWarning]]:
    group_state, person_state = states.group, states.person
    for slot, member_id in moves:
        group_state = overlay_candidate_assignment(
            group_state, slot=slot, team_member_id=member_id, assignment_id=None
        )
        person_state = overlay_candidate_assignment(
            person_state, slot=slot, team_member_id=member_id, assignment_id=None
        )
    slot_ids = {slot.id for slot, _member_id in moves}
    findings = [
        warning
        for warning in evaluate_plan_state(group_state, db=db, statutory_state=person_state)
        if _finding_involves_swap(warning, member_ids=member_ids, slot_ids=slot_ids)
    ]
    errors = [row for row in findings if row.severity == "error"]
    warnings = [row for row in findings if row.severity != "error"]
    return errors, warnings


def _swap_plan_states(
    db: Session,
    *,
    organization_id: int,
    start_date: date,
    end_date: date,
    shift_group_id: int | None,
) -> _SwapStates:
    # Statutory rules are about the person, so they see duties in every group, as assignment
    # preflight does. Roster rules keep the group scope because the cells and intents they
    # match against are loaded for the swap's group only.
    window = {
        "organization_id": organization_id,
        "start_date": start_date,
        "end_date": end_date,
        "shift_group_id": shift_group_id,
    }
    return _SwapStates(
        group=build_plan_state(db, **window),
        person=build_plan_state(db, **window, member_duties_org_wide=True),
    )


def evaluate_swap_legality(
    db: Session,
    row: ShiftSwapRequest,
    *,
    incoming_member_id: int,
) -> tuple[list[ValidationWarning], list[ValidationWarning]]:
    offered_slot = _load_slot(db, row.offered_slot_id, organization_id=row.organization_id)
    counterparty_slot = None
    if row.counterparty_slot_id is not None:
        counterparty_slot = _load_slot(db, row.counterparty_slot_id, organization_id=row.organization_id)
    dates = [offered_slot.slot_date]
    if counterparty_slot is not None:
        dates.append(counterparty_slot.slot_date)
    states = _swap_plan_states(
        db,
        organization_id=row.organization_id,
        start_date=min(dates),
        end_date=max(dates),
        shift_group_id=row.shift_group_id,
    )
    moves = [(offered_slot, incoming_member_id)]
    if counterparty_slot is not None:
        moves.append((counterparty_slot, row.offered_by_team_member_id))
    return _swap_findings(
        db,
        states,
        moves=moves,
        member_ids={row.offered_by_team_member_id, incoming_member_id},
    )


def _require_legal(
    db: Session,
    row: ShiftSwapRequest,
    *,
    incoming_member_id: int,
) -> list[ValidationWarning]:
    errors, warnings = evaluate_swap_legality(db, row, incoming_member_id=incoming_member_id)
    if errors:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_ILLEGAL",
            errors[0].message,
            findings=errors,
        )
    return warnings


def eligible_member_ids_for_slot(
    db: Session,
    slot: RosterSlot,
    *,
    organization_id: int,
    shift_group_id: int | None = None,
) -> set[int]:
    state = build_plan_state(
        db,
        organization_id=organization_id,
        start_date=slot.slot_date,
        end_date=slot.slot_date,
        shift_group_id=shift_group_id,
    )
    from app.services.solver.model import eligible_members_for_slots

    by_slot = eligible_members_for_slots(db, state=state, target_slots=[slot])
    return set(by_slot.get(slot.id, set()))


def legal_member_ids_for_slot(
    db: Session,
    slot: RosterSlot,
    candidate_ids: set[int],
    *,
    organization_id: int,
    shift_group_id: int | None = None,
    offered_by_team_member_id: int | None = None,
) -> set[int]:
    """Candidates whose taking ``slot`` produces no error finding, as claim would check it.

    The CP-SAT mask does not encode every statutory rule yet (``min_rest_period`` and
    ``rest_after_long_duty`` are tier B), so a masked-in member can still be refused at claim.
    """
    if not candidate_ids:
        return set()
    states = _swap_plan_states(
        db,
        organization_id=organization_id,
        start_date=slot.slot_date,
        end_date=slot.slot_date,
        shift_group_id=shift_group_id,
    )
    legal: set[int] = set()
    for member_id in candidate_ids:
        member_ids = {member_id}
        if offered_by_team_member_id is not None:
            member_ids.add(offered_by_team_member_id)
        errors, _warnings = _swap_findings(
            db,
            states,
            moves=[(slot, member_id)],
            member_ids=member_ids,
        )
        if not errors:
            legal.add(member_id)
    return legal


def _slot_is_night_duty(slot: RosterSlot) -> bool:
    if slot.ends_at is not None and slot.ends_at.date() > slot.slot_date:
        return True
    return slot.starts_at is not None and slot.starts_at.hour >= NIGHT_AFTER_HOUR


def _slot_is_weekend_or_holiday(slot: RosterSlot) -> bool:
    if slot.day_class in {"weekend", "holiday"}:
        return True
    return classify_day(slot.slot_date) in {"weekend", "holiday"}


def _slot_category(slot: RosterSlot) -> str | None:
    template = slot.shift_template
    if template is None:
        return None
    return template.category


def _dimension_match_score(
    slot: RosterSlot,
    dimension: FairnessDimension,
    *,
    night: bool,
    weekend: bool,
) -> int:
    category = _slot_category(slot)
    if dimension.metric == "statutory_minutes":
        return -1
    if dimension.night and not night:
        return -1
    if dimension.day_filter == "weekend_holiday" and not weekend:
        return -1
    if dimension.category and dimension.category != category:
        return -1
    score = 0
    if night and dimension.night:
        score += 8
    if weekend and dimension.day_filter == "weekend_holiday":
        score += 4
    if dimension.category and dimension.category == category:
        score += 2
    if not dimension.night and dimension.day_filter == "any" and not dimension.category:
        score += 1
    return score


def relevant_fairness_dimension_for_slot(
    slot: RosterSlot,
    dimensions: list[FairnessDimension],
) -> FairnessDimension | None:
    night = _slot_is_night_duty(slot)
    weekend = _slot_is_weekend_or_holiday(slot)
    best: FairnessDimension | None = None
    best_score = 0
    for dimension in dimensions:
        score = _dimension_match_score(slot, dimension, night=night, weekend=weekend)
        if score > best_score:
            best_score = score
            best = dimension
    if best is not None:
        return best
    for dimension in dimensions:
        if dimension.id == "duties":
            return dimension
    for dimension in dimensions:
        if (
            dimension.metric == "duty_count"
            and not dimension.night
            and dimension.day_filter == "any"
            and not dimension.category
        ):
            return dimension
    return None


def rank_eligible_member_ids(
    eligible: set[int],
    accounts: FairnessAccountsRead,
    slot: RosterSlot,
) -> list[int]:
    dimension = relevant_fairness_dimension_for_slot(slot, list(accounts.dimensions))
    if dimension is None:
        return sorted(eligible)
    by_member: dict[int, float] = {}
    for member in accounts.members:
        value = next(
            (row for row in member.dimensions if row.dimension_id == dimension.id),
            None,
        )
        by_member[member.team_member_id] = value.deviation_absolute if value is not None else 0.0
    return sorted(eligible, key=lambda member_id: (by_member.get(member_id, 0.0), member_id))


def list_eligible_claimants(
    db: Session,
    *,
    roster_slot_id: int,
    organization_id: int,
    shift_group_id: int | None = None,
    exclude_team_member_id: int | None = None,
) -> list[int]:
    slot = _load_slot(db, roster_slot_id, organization_id=organization_id)
    if shift_group_id is not None:
        _assert_slot_in_group(db, slot, shift_group_id)
    eligible = eligible_member_ids_for_slot(
        db,
        slot,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
    )
    if exclude_team_member_id is not None:
        eligible.discard(exclude_team_member_id)
    eligible = legal_member_ids_for_slot(
        db,
        slot,
        eligible,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
        offered_by_team_member_id=exclude_team_member_id,
    )
    try:
        accounts = build_fairness_accounts(
            db,
            slot.planning_period_id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
        )
        return rank_eligible_member_ids(eligible, accounts, slot)
    except Exception:
        return sorted(eligible)


def _assert_member_eligible(
    db: Session,
    slot: RosterSlot,
    *,
    organization_id: int,
    shift_group_id: int,
    team_member_id: int,
) -> None:
    eligible = eligible_member_ids_for_slot(
        db,
        slot,
        organization_id=organization_id,
        shift_group_id=shift_group_id,
    )
    if team_member_id not in eligible:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_INELIGIBLE",
            "Team member is not eligible to take this duty",
        )


def eligible_member_ids_for_request(db: Session, row: ShiftSwapRequest) -> list[int]:
    if row.kind != SWAP_KIND_GIVEAWAY or row.status not in {SWAP_STATUS_DRAFT, SWAP_STATUS_OPEN}:
        return []
    slot = db.get(RosterSlot, row.offered_slot_id)
    if slot is None:
        return []
    return list_eligible_claimants(
        db,
        roster_slot_id=slot.id,
        organization_id=row.organization_id,
        shift_group_id=row.shift_group_id,
        exclude_team_member_id=row.offered_by_team_member_id,
    )


def get_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
) -> ShiftSwapRequest:
    row = db.get(ShiftSwapRequest, request_id)
    if row is None or row.organization_id != organization_id:
        raise ShiftSwapNotFoundError("Shift swap request not found")
    return row


def list_shift_swaps(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None = None,
    status: str | None = None,
    statuses: Sequence[str] | None = None,
    kind: str | None = None,
    viewer_team_member_id: int | None = None,
    planner_shift_group_ids: set[int] | None = None,
) -> list[ShiftSwapRequest]:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    stmt = select(ShiftSwapRequest).where(
        ShiftSwapRequest.organization_id == organization_id,
        ShiftSwapRequest.planning_period_id == planning_period_id,
    )
    if shift_group_id is not None:
        stmt = stmt.where(ShiftSwapRequest.shift_group_id == shift_group_id)
    if statuses:
        stmt = stmt.where(ShiftSwapRequest.status.in_(list(statuses)))
    elif status is not None:
        stmt = stmt.where(ShiftSwapRequest.status == status)
    if kind is not None:
        stmt = stmt.where(ShiftSwapRequest.kind == kind)
    if planner_shift_group_ids is not None:
        if not planner_shift_group_ids:
            return []
        stmt = stmt.where(ShiftSwapRequest.shift_group_id.in_(planner_shift_group_ids))
    if viewer_team_member_id is not None:
        member_groups = set(
            db.scalars(
                select(PlanningPeriodShiftGroupMember.shift_group_id).where(
                    PlanningPeriodShiftGroupMember.planning_period_id == planning_period_id,
                    PlanningPeriodShiftGroupMember.team_member_id == viewer_team_member_id,
                )
            ).all()
        )
        stmt = stmt.where(
            or_(
                ShiftSwapRequest.offered_by_team_member_id == viewer_team_member_id,
                ShiftSwapRequest.target_team_member_id == viewer_team_member_id,
                (
                    (ShiftSwapRequest.kind == SWAP_KIND_GIVEAWAY)
                    & (ShiftSwapRequest.status == SWAP_STATUS_OPEN)
                    & ShiftSwapRequest.shift_group_id.in_(member_groups or {-1})
                ),
            )
        )
    stmt = stmt.order_by(ShiftSwapRequest.id.desc())
    return list(db.scalars(stmt).all())


def unresolved_shift_swap_to_read(
    row: ShiftSwapRequest,
    offered_slot: RosterSlot,
    *,
    today: date | None = None,
    eligible_member_ids: list[int] | None = None,
) -> ShiftSwapUnresolvedRead:
    as_of = today if today is not None else _utc_today()
    payload = shift_swap_to_read(row, eligible_member_ids=eligible_member_ids)
    return ShiftSwapUnresolvedRead(
        **payload.model_dump(),
        duty_date=offered_slot.slot_date,
        days_until_duty=(offered_slot.slot_date - as_of).days,
        request_age_days=(as_of - _as_utc_date(row.created_at)).days,
    )


def list_unresolved_shift_swaps(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int,
    planner_shift_group_ids: set[int] | None = None,
) -> list[ShiftSwapUnresolvedRead]:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    require_shift_group(db, shift_group_id, organization_id)
    if planner_shift_group_ids is not None and (
        not planner_shift_group_ids or shift_group_id not in planner_shift_group_ids
    ):
        return []
    stmt = (
        select(ShiftSwapRequest, RosterSlot)
        .join(RosterSlot, RosterSlot.id == ShiftSwapRequest.offered_slot_id)
        .where(
            ShiftSwapRequest.organization_id == organization_id,
            ShiftSwapRequest.planning_period_id == planning_period_id,
            ShiftSwapRequest.shift_group_id == shift_group_id,
            ShiftSwapRequest.status.in_(UNRESOLVED_STATUSES),
        )
        .order_by(RosterSlot.slot_date.asc(), ShiftSwapRequest.id.asc())
    )
    today = _utc_today()
    return [
        unresolved_shift_swap_to_read(
            row,
            slot,
            today=today,
            eligible_member_ids=[],
        )
        for row, slot in db.execute(stmt).all()
    ]


def create_shift_swap(
    db: Session,
    payload: ShiftSwapRequestCreate,
    *,
    organization_id: int,
    offered_by_team_member_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None,
) -> ShiftSwapRequest:
    require_planning_period_in_org(db, payload.planning_period_id, organization_id)
    _require_visible_group_status(
        db,
        planning_period_id=payload.planning_period_id,
        shift_group_id=payload.shift_group_id,
        organization_id=organization_id,
    )
    offered_slot = _load_slot(db, payload.offered_slot_id, organization_id=organization_id)
    if offered_slot.planning_period_id != payload.planning_period_id:
        raise ValueError("Roster slot is not in this planning period")
    _assert_slot_in_group(db, offered_slot, payload.shift_group_id)
    assignment = _assignment_for_slot(db, offered_slot.id)
    if assignment is None or assignment.team_member_id != offered_by_team_member_id:
        raise ShiftSwapConflictError("SHIFT_SWAP_NOT_OWNER", "You can only offer a duty assigned to you")
    if offered_slot.slot_date < _utc_today():
        raise ShiftSwapConflictError("SHIFT_SWAP_EXPIRED", "Cannot offer a duty on a past date")
    if _active_request_for_slot(db, offered_slot_id=offered_slot.id) is not None:
        raise ShiftSwapConflictError("SHIFT_SWAP_ALREADY_OPEN", "This duty already has an open swap request")
    if payload.kind == SWAP_KIND_DIRECT:
        if payload.target_team_member_id is None:
            raise ValueError("target_team_member_id is required for a direct swap")
        if payload.target_team_member_id == offered_by_team_member_id:
            raise ValueError("Cannot propose a direct swap to yourself")
        target = db.get(TeamMember, payload.target_team_member_id)
        if target is None or target.organization_id != organization_id:
            raise ValueError("Target team member not found")
    elif payload.target_team_member_id is not None:
        raise ValueError("target_team_member_id is only valid for a direct swap")
    counterparty_slot = None
    if payload.counterparty_slot_id is not None:
        if payload.kind != SWAP_KIND_DIRECT:
            raise ValueError("counterparty_slot_id is only valid for a direct swap")
        counterparty_slot = _load_slot(db, payload.counterparty_slot_id, organization_id=organization_id)
        if counterparty_slot.planning_period_id != payload.planning_period_id:
            raise ValueError("Counterparty slot is not in this planning period")
        _assert_slot_in_group(db, counterparty_slot, payload.shift_group_id)
        other_assignment = _assignment_for_slot(db, counterparty_slot.id)
        if other_assignment is None or other_assignment.team_member_id != payload.target_team_member_id:
            raise ValueError("Counterparty slot is not assigned to the target team member")
    row = ShiftSwapRequest(
        organization_id=organization_id,
        planning_period_id=payload.planning_period_id,
        shift_group_id=payload.shift_group_id,
        kind=payload.kind,
        status=SWAP_STATUS_DRAFT,
        offered_by_team_member_id=offered_by_team_member_id,
        offered_slot_id=offered_slot.id,
        target_team_member_id=payload.target_team_member_id if payload.kind == SWAP_KIND_DIRECT else None,
        counterparty_slot_id=counterparty_slot.id if counterparty_slot is not None else None,
        warning_findings=[],
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={"kind": row.kind, "offered_slot_id": row.offered_slot_id},
    )
    db.commit()
    db.refresh(row)
    if payload.open_immediately:
        return open_shift_swap(
            db,
            row.id,
            organization_id=organization_id,
            actor=actor,
            source=source,
            actor_team_member_id=offered_by_team_member_id,
        )
    return row


def open_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
    actor_team_member_id: int | None,
) -> ShiftSwapRequest:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    if actor_team_member_id is not None and row.offered_by_team_member_id != actor_team_member_id:
        raise PermissionError("Only the offering member can open this request")
    offered_slot = _load_slot(db, row.offered_slot_id, organization_id=organization_id)
    _expire_if_past(db, row, offered_slot)
    if row.kind == SWAP_KIND_GIVEAWAY:
        _assert_transition(row, SWAP_STATUS_OPEN)
        claimants = list_eligible_claimants(
            db,
            roster_slot_id=offered_slot.id,
            organization_id=organization_id,
            shift_group_id=row.shift_group_id,
            exclude_team_member_id=row.offered_by_team_member_id,
        )
        if not claimants:
            raise ShiftSwapConflictError(
                "SHIFT_SWAP_NO_ELIGIBLE_CLAIMANT",
                "No eligible team member can claim this duty",
            )
        row.status = SWAP_STATUS_OPEN
    else:
        _assert_transition(row, SWAP_STATUS_TARGETED)
        if row.target_team_member_id is None:
            raise ValueError("target_team_member_id is required for a direct swap")
        _assert_member_eligible(
            db,
            offered_slot,
            organization_id=organization_id,
            shift_group_id=row.shift_group_id,
            team_member_id=row.target_team_member_id,
        )
        if row.counterparty_slot_id is not None:
            counterparty = _load_slot(db, row.counterparty_slot_id, organization_id=organization_id)
            _assert_member_eligible(
                db,
                counterparty,
                organization_id=organization_id,
                shift_group_id=row.shift_group_id,
                team_member_id=row.offered_by_team_member_id,
            )
        warnings = _require_legal(db, row, incoming_member_id=row.target_team_member_id)
        row.warning_findings = _dump_findings(warnings)
        row.status = SWAP_STATUS_TARGETED
    record_audit(
        db,
        actor=actor,
        source=source,
        action="open",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={"status": row.status},
    )
    db.commit()
    db.refresh(row)
    return row


def claim_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    claimer_team_member_id: int,
    actor: str,
    source: str,
) -> ShiftSwapRequest:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    offered_slot = _load_slot(db, row.offered_slot_id, organization_id=organization_id)
    _expire_if_past(db, row, offered_slot)
    if row.kind != SWAP_KIND_GIVEAWAY:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_INVALID_TRANSITION",
            "Only an open giveaway can be claimed",
        )
    if row.status != SWAP_STATUS_OPEN:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_CONFLICT",
            "This giveaway was already claimed",
        )
    if claimer_team_member_id == row.offered_by_team_member_id:
        raise ShiftSwapConflictError("SHIFT_SWAP_INELIGIBLE", "You cannot claim your own duty")
    _assert_member_eligible(
        db,
        offered_slot,
        organization_id=organization_id,
        shift_group_id=row.shift_group_id,
        team_member_id=claimer_team_member_id,
    )
    warnings = _require_legal(db, row, incoming_member_id=claimer_team_member_id)
    result = db.execute(
        update(ShiftSwapRequest)
        .where(
            ShiftSwapRequest.id == request_id,
            ShiftSwapRequest.organization_id == organization_id,
            ShiftSwapRequest.kind == SWAP_KIND_GIVEAWAY,
            ShiftSwapRequest.status == SWAP_STATUS_OPEN,
        )
        .values(
            status=SWAP_STATUS_CLAIMED,
            target_team_member_id=claimer_team_member_id,
            warning_findings=_dump_findings(warnings),
        )
    )
    if result.rowcount != 1:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_CONFLICT",
            "This giveaway was already claimed",
        )
    record_audit(
        db,
        actor=actor,
        source=source,
        action="claim",
        entity_type="shift_swap_request",
        entity_id=request_id,
        details={"claimed_by_team_member_id": claimer_team_member_id},
    )
    db.commit()
    return get_shift_swap(db, request_id, organization_id=organization_id)


def accept_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    actor_team_member_id: int,
    actor: str,
    source: str,
) -> ShiftSwapRequest:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    offered_slot = _load_slot(db, row.offered_slot_id, organization_id=organization_id)
    _expire_if_past(db, row, offered_slot)
    if row.kind != SWAP_KIND_DIRECT or row.status != SWAP_STATUS_TARGETED:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_INVALID_TRANSITION",
            "Only a targeted direct swap can be accepted",
        )
    if row.target_team_member_id != actor_team_member_id:
        raise PermissionError("Only the named member can accept this swap")
    _assert_member_eligible(
        db,
        offered_slot,
        organization_id=organization_id,
        shift_group_id=row.shift_group_id,
        team_member_id=actor_team_member_id,
    )
    if row.counterparty_slot_id is not None:
        counterparty = _load_slot(db, row.counterparty_slot_id, organization_id=organization_id)
        _assert_member_eligible(
            db,
            counterparty,
            organization_id=organization_id,
            shift_group_id=row.shift_group_id,
            team_member_id=row.offered_by_team_member_id,
        )
    warnings = _require_legal(db, row, incoming_member_id=actor_team_member_id)
    _assert_transition(row, SWAP_STATUS_ACCEPTED)
    row.status = SWAP_STATUS_ACCEPTED
    row.warning_findings = _dump_findings(warnings)
    record_audit(
        db,
        actor=actor,
        source=source,
        action="accept",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={},
    )
    db.commit()
    db.refresh(row)
    return row


def withdraw_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    actor_team_member_id: int | None,
    actor: str,
    source: str,
    allow_planner: bool = False,
) -> ShiftSwapRequest:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    if not allow_planner and (actor_team_member_id is None or row.offered_by_team_member_id != actor_team_member_id):
        raise PermissionError("Only the offering member can withdraw this request")
    _assert_transition(row, SWAP_STATUS_WITHDRAWN)
    row.status = SWAP_STATUS_WITHDRAWN
    record_audit(
        db,
        actor=actor,
        source=source,
        action="withdraw",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={},
    )
    db.commit()
    db.refresh(row)
    return row


def reject_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
    resolved_by_user_id: int | None,
    actor_team_member_id: int | None = None,
    allow_planner: bool = False,
) -> ShiftSwapRequest:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    if not allow_planner:
        if row.kind != SWAP_KIND_DIRECT or row.status != SWAP_STATUS_TARGETED:
            raise ShiftSwapConflictError(
                "SHIFT_SWAP_INVALID_TRANSITION",
                "Only the named member can decline a targeted direct swap",
            )
        if actor_team_member_id is None or row.target_team_member_id != actor_team_member_id:
            raise PermissionError("Only the named member can decline this swap")
    _assert_transition(row, SWAP_STATUS_REJECTED)
    row.status = SWAP_STATUS_REJECTED
    row.resolved_by_user_id = resolved_by_user_id
    record_audit(
        db,
        actor=actor,
        source=source,
        action="reject",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={},
    )
    db.commit()
    db.refresh(row)
    return row


def approve_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
    resolved_by_user_id: int | None,
) -> ShiftSwapRequest:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    incoming = _incoming_member_id(row)
    if incoming is None:
        raise ShiftSwapConflictError("SHIFT_SWAP_INVALID_TRANSITION", "Swap has no counterparty yet")
    offered_slot = _load_slot(db, row.offered_slot_id, organization_id=organization_id)
    _expire_if_past(db, row, offered_slot)
    if row.status not in {SWAP_STATUS_CLAIMED, SWAP_STATUS_ACCEPTED}:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_INVALID_TRANSITION",
            "Only a claimed giveaway or accepted direct swap can be approved",
        )
    _assert_member_eligible(
        db,
        offered_slot,
        organization_id=organization_id,
        shift_group_id=row.shift_group_id,
        team_member_id=incoming,
    )
    warnings = _require_legal(db, row, incoming_member_id=incoming)
    _assert_transition(row, SWAP_STATUS_APPROVED)
    row.status = SWAP_STATUS_APPROVED
    row.warning_findings = _dump_findings(warnings)
    row.resolved_by_user_id = resolved_by_user_id
    record_audit(
        db,
        actor=actor,
        source=source,
        action="approve",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={},
    )
    db.commit()
    db.refresh(row)
    return row


def apply_shift_swap(
    db: Session,
    request_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
    applied_by_user_id: int | None,
) -> tuple[ShiftSwapRequest, list[RosterSlotAssignment], PlanningPlanVersion]:
    row = get_shift_swap(db, request_id, organization_id=organization_id)
    incoming = _incoming_member_id(row)
    if incoming is None:
        raise ShiftSwapConflictError("SHIFT_SWAP_INVALID_TRANSITION", "Swap has no counterparty yet")
    if row.status != SWAP_STATUS_APPROVED:
        raise ShiftSwapConflictError(
            "SHIFT_SWAP_INVALID_TRANSITION",
            "Only an approved swap can be applied",
        )
    offered_slot = _load_slot(db, row.offered_slot_id, organization_id=organization_id)
    _assert_member_eligible(
        db,
        offered_slot,
        organization_id=organization_id,
        shift_group_id=row.shift_group_id,
        team_member_id=incoming,
    )
    warnings = _require_legal(db, row, incoming_member_id=incoming)
    assignments: list[RosterSlotAssignment] = []
    written_members: list[int] = []
    window_dates = [offered_slot.slot_date]
    assignments.append(
        upsert_roster_slot_assignment(
            db,
            RosterSlotAssignmentUpsert(roster_slot_id=offered_slot.id, team_member_id=incoming),
            organization_id=organization_id,
            actor=actor,
            source=SWAP_ASSIGNMENT_SOURCE,
            commit=False,
            enforce_preflight=False,
        )
    )
    written_members.extend([incoming, row.offered_by_team_member_id])
    if row.counterparty_slot_id is not None:
        counterparty = _load_slot(db, row.counterparty_slot_id, organization_id=organization_id)
        window_dates.append(counterparty.slot_date)
        assignments.append(
            upsert_roster_slot_assignment(
                db,
                RosterSlotAssignmentUpsert(
                    roster_slot_id=counterparty.id,
                    team_member_id=row.offered_by_team_member_id,
                ),
                organization_id=organization_id,
                actor=actor,
                source=SWAP_ASSIGNMENT_SOURCE,
                commit=False,
                enforce_preflight=False,
            )
        )
    version = snapshot_swap_apply_plan_version(
        db,
        planning_period_id=row.planning_period_id,
        shift_group_id=row.shift_group_id,
        organization_id=organization_id,
        created_by_user_id=applied_by_user_id,
        actor=actor,
        source=source,
        note=f"Applied shift swap {row.id}",
    )
    row.status = SWAP_STATUS_APPLIED
    row.warning_findings = _dump_findings(warnings)
    row.resolved_by_user_id = applied_by_user_id
    row.applied_plan_version_id = version.id
    record_audit(
        db,
        actor=actor,
        source=source,
        action="apply",
        entity_type="shift_swap_request",
        entity_id=row.id,
        details={"plan_version_id": version.id},
    )
    db.commit()
    refresh_derived_window(
        db,
        organization_id=organization_id,
        member_ids=sorted(set(written_members)),
        start_date=min(window_dates),
        end_date=max(window_dates),
    )
    db.refresh(row)
    for assignment in assignments:
        db.refresh(assignment)
    db.refresh(version)
    return row, assignments, version


def applied_swap_to_read(
    row: ShiftSwapRequest,
    assignments: list[RosterSlotAssignment],
    version: PlanningPlanVersion,
) -> ShiftSwapApplyRead:
    return ShiftSwapApplyRead(
        request=shift_swap_to_read(row),
        assignments=[RosterSlotAssignmentRead.model_validate(item) for item in assignments],
        plan_version=PlanVersionRead.model_validate(version),
    )
