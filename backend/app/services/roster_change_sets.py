from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import (
    RosterChangeSet,
    RosterChangeSetItem,
    RosterSlot,
    RosterSlotAssignment,
    TeamMember,
)
from app.schemas import RosterSlotAssignmentClear, RosterSlotAssignmentUpsert, ValidationWarning
from app.services.audit import record_audit
from app.services.planning import can_edit_planning_data, get_shift_group_planning_status
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group
from app.services.roster_matrix import (
    _team_member_has_template_no_go,
    _warning_targets_slot,
    clear_roster_slot_assignment,
    lock_roster_slots_for_assignment,
    upsert_roster_slot_assignment,
)
from app.services.rules import build_plan_state, evaluate_plan_state
from app.services.rules.shift_constraints import (
    overlay_candidate_assignment,
    overlay_clear_assignment,
)
from app.services.shift_groups import shift_group_ids_for_template, team_member_may_cover_template
from app.services.tenancy import require_planning_period_in_org

MAX_CHANGE_SET_ITEMS = 500
COUPLED_SHIFT_WINDOW = timedelta(days=7)
SOURCE_UI = "ui"
MODE_ALL_OR_NOTHING = "all_or_nothing"
MODE_BEST_EFFORT = "best_effort"
STATUS_APPLIED = "applied"
STATUS_REFUSED = "refused"
STATUS_PARTIAL = "partially_applied"
STATUS_REVERTED = "reverted"
OUTCOME_APPLIED = "applied"
OUTCOME_REFUSED = "refused"
OUTCOME_UNCHANGED = "unchanged"


class RosterChangeSetError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RosterChangeInput:
    roster_slot_id: int
    team_member_id: int | None
    manual_override: bool = False
    comment: str | None = None


@dataclass(frozen=True)
class AssignmentSnapshot:
    team_member_id: int | None
    manual_override: bool
    comment: str | None


def apply_roster_change_set(
    db: Session,
    *,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None,
    items: Sequence[RosterChangeInput],
    mode: str,
    actor: str,
    source: str,
    created_by_user_id: int | None,
    label: str | None = None,
    reverts_change_set_id: int | None = None,
    before_commit: Callable[[RosterChangeSet], None] | None = None,
    forced_refusals: dict[int, str] | None = None,
    expected_current: dict[int, AssignmentSnapshot] | None = None,
) -> RosterChangeSet:
    if mode not in (MODE_ALL_OR_NOTHING, MODE_BEST_EFFORT):
        raise RosterChangeSetError("INVALID_MODE", "mode must be all_or_nothing or best_effort")
    if len(items) > MAX_CHANGE_SET_ITEMS:
        raise RosterChangeSetError("TOO_MANY_ITEMS", "A change set can contain at most 500 items")
    require_planning_period_in_org(db, planning_period_id, organization_id)
    change_set = RosterChangeSet(
        organization_id=organization_id,
        planning_period_id=planning_period_id,
        shift_group_id=shift_group_id,
        created_by_user_id=created_by_user_id,
        actor=actor,
        source=source,
        mode=mode,
        status=STATUS_REFUSED,
        reverts_change_set_id=reverts_change_set_id,
        label=label,
    )
    db.add(change_set)
    db.flush()
    slot_ids = [item.roster_slot_id for item in items]
    lock_roster_slots_for_assignment(db, slot_ids)
    slots = {
        row.id: row
        for row in db.scalars(
            select(RosterSlot)
            .where(RosterSlot.id.in_(slot_ids or [-1]))
            .options(joinedload(RosterSlot.shift_template), joinedload(RosterSlot.planning_period))
        ).unique()
    }
    current_assignments = {
        row.roster_slot_id: row
        for row in db.scalars(
            select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id.in_(slot_ids or [-1]))
        )
    }
    rows: list[RosterChangeSetItem] = []
    for item in items:
        slot = slots.get(item.roster_slot_id)
        current = current_assignments.get(item.roster_slot_id)
        row = RosterChangeSetItem(
            change_set_id=change_set.id,
            roster_slot_id=item.roster_slot_id,
            before_team_member_id=current.team_member_id if current is not None else None,
            after_team_member_id=item.team_member_id,
            before_manual_override=bool(current.manual_override) if current is not None else False,
            after_manual_override=item.manual_override,
            before_comment=current.comment if current is not None else None,
            after_comment=item.comment,
            outcome=OUTCOME_APPLIED,
            findings=[],
            refusal_code=None,
        )
        refusal = None
        expected = expected_current.get(item.roster_slot_id) if expected_current else None
        if forced_refusals and item.roster_slot_id in forced_refusals:
            refusal = forced_refusals[item.roster_slot_id]
        elif expected is not None and not _snapshot_matches(current, expected):
            refusal = "changed_since"
        else:
            refusal = _precheck(db, organization_id, planning_period_id, shift_group_id, slot, item)
        if refusal is not None:
            row.outcome = OUTCOME_REFUSED
            row.refusal_code = refusal
        elif _same_as_before(row):
            row.outcome = OUTCOME_UNCHANGED
        rows.append(row)
        db.add(row)
    if _any_target_group_published(db, organization_id, planning_period_id, shift_group_id, list(slots.values())):
        for row in rows:
            row.outcome = OUTCOME_REFUSED
            row.refusal_code = "PUBLISHED"
    db.flush()
    if not rows:
        change_set.status = STATUS_APPLIED
        if before_commit is not None:
            before_commit(change_set)
        db.commit()
        db.refresh(change_set)
        return change_set
    _evaluate_legal_subset(db, organization_id, rows, slots, mode)
    _refuse_if_expected_changed(db, rows, expected_current)
    if mode == MODE_ALL_OR_NOTHING and any(row.outcome == OUTCOME_REFUSED for row in rows):
        for row in rows:
            if row.outcome != OUTCOME_REFUSED:
                row.outcome = OUTCOME_REFUSED
                row.refusal_code = row.refusal_code or "SET_REFUSED"
        change_set.status = STATUS_REFUSED
    else:
        _write_rows(
            db,
            organization_id,
            actor,
            source,
            rows,
            slots,
            mode=mode,
            expected_current=expected_current,
        )
        db.flush()
        applied = [row for row in rows if row.outcome == OUTCOME_APPLIED]
        refused = [row for row in rows if row.outcome == OUTCOME_REFUSED]
        if applied and refused:
            change_set.status = STATUS_PARTIAL
        elif applied or (rows and not refused):
            change_set.status = STATUS_APPLIED
        else:
            change_set.status = STATUS_REFUSED
        if applied:
            member_ids = sorted(
                {
                    member_id
                    for row in applied
                    for member_id in (row.before_team_member_id, row.after_team_member_id)
                    if member_id is not None
                }
            )
            dates = [slots[row.roster_slot_id].slot_date for row in applied if row.roster_slot_id in slots]
            if member_ids and dates:
                from app.services.time_entries import refresh_derived_window

                refresh_derived_window(
                    db,
                    organization_id=organization_id,
                    member_ids=member_ids,
                    start_date=min(dates),
                    end_date=max(dates),
                    commit=False,
                )
            record_audit(
                db,
                actor=actor,
                source=source,
                action="apply",
                entity_type="roster_change_set",
                entity_id=change_set.id,
                details={"item_count": len(applied), "mode": mode},
            )
    if before_commit is not None:
        before_commit(change_set)
    db.commit()
    db.refresh(change_set)
    return change_set


def revert_roster_change_set(
    db: Session,
    change_set_id: int,
    *,
    organization_id: int,
    actor: str,
    source: str,
    created_by_user_id: int | None,
    mode: str = MODE_ALL_OR_NOTHING,
) -> RosterChangeSet:
    original = db.get(RosterChangeSet, change_set_id)
    if original is None or original.organization_id != organization_id:
        raise RosterChangeSetError("NOT_FOUND", "Roster change set not found")
    restore: list[RosterChangeInput] = []
    expected_current: dict[int, AssignmentSnapshot] = {}
    for item in original.items:
        if item.outcome != OUTCOME_APPLIED:
            continue
        expected_current[item.roster_slot_id] = AssignmentSnapshot(
            team_member_id=item.after_team_member_id,
            manual_override=item.after_manual_override,
            comment=item.after_comment,
        )
        restore.append(
            RosterChangeInput(
                roster_slot_id=item.roster_slot_id,
                team_member_id=item.before_team_member_id,
                manual_override=item.before_manual_override,
                comment=item.before_comment,
            )
        )
    if not restore:
        raise RosterChangeSetError("NOTHING_TO_REVERT", "Roster change set has no applied items")

    def mark(change_set: RosterChangeSet) -> None:
        if change_set.status == STATUS_APPLIED:
            original.status = STATUS_REVERTED

    return apply_roster_change_set(
        db,
        organization_id=organization_id,
        planning_period_id=original.planning_period_id,
        shift_group_id=original.shift_group_id,
        items=restore,
        mode=mode,
        actor=actor,
        source=source,
        created_by_user_id=created_by_user_id,
        label=f"Revert {original.id}",
        reverts_change_set_id=original.id,
        before_commit=mark,
        expected_current=expected_current,
    )


def list_roster_change_sets(
    db: Session,
    planning_period_id: int,
    shift_group_id: int | None,
    *,
    organization_id: int,
    limit: int = 50,
) -> list[RosterChangeSet]:
    require_planning_period_in_org(db, planning_period_id, organization_id)
    stmt = (
        select(RosterChangeSet)
        .where(
            RosterChangeSet.organization_id == organization_id,
            RosterChangeSet.planning_period_id == planning_period_id,
        )
        .order_by(RosterChangeSet.id.desc())
        .limit(limit)
    )
    if shift_group_id is not None:
        stmt = stmt.where(RosterChangeSet.shift_group_id == shift_group_id)
    return list(db.scalars(stmt).unique())


def legacy_refusal_message(row: RosterChangeSetItem) -> str:
    messages = {
        "CANNOT_COVER_TEMPLATE": "Team member is not a member of a shift group that covers this template",
        "NOT_ON_ROSTER": "Team member is not on the roster for this planning period and shift group",
        "TEMPLATE_NO_GO": "Team member marked this shift template as a no-go on that day",
        "SLOT_NOT_FOUND": "Roster slot not found",
        "SLOT_WRONG_PERIOD": "Roster slot not found",
        "SLOT_OUTSIDE_GROUP": "Roster slot is not in the selected shift group",
    }
    if row.refusal_code in messages:
        return messages[row.refusal_code]
    findings = row.findings or []
    for finding in findings:
        if finding.get("severity") == "error" and finding.get("message"):
            return str(finding["message"])
    return row.refusal_code or "Assignment refused"


def _precheck(
    db: Session,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None,
    slot: RosterSlot | None,
    item: RosterChangeInput,
) -> str | None:
    if slot is None:
        return "SLOT_NOT_FOUND"
    if slot.planning_period_id != planning_period_id or slot.planning_period.organization_id != organization_id:
        period = slot.planning_period
        if period is None or period.organization_id != organization_id or slot.planning_period_id != planning_period_id:
            return "SLOT_WRONG_PERIOD"
    if shift_group_id is not None and slot.shift_template_id is not None:
        covered = shift_group_ids_for_template(db, slot.shift_template_id)
        if covered and shift_group_id not in covered:
            return "SLOT_OUTSIDE_GROUP"
    if item.team_member_id is None:
        return None
    if db.get(TeamMember, item.team_member_id) is None:
        return "NOT_ON_ROSTER"
    if not team_member_may_cover_template(db, team_member_id=item.team_member_id, shift_template_id=slot.shift_template_id):
        return "CANNOT_COVER_TEMPLATE"
    group_ids = shift_group_ids_for_template(db, slot.shift_template_id) if slot.shift_template_id is not None else set()
    if group_ids:
        on_roster = any(
            item.team_member_id
            in team_member_ids_for_period_shift_group(
                db, planning_period_id=slot.planning_period_id, shift_group_id=group_id
            )
            for group_id in group_ids
        )
        if not on_roster:
            return "NOT_ON_ROSTER"
    if not item.manual_override and _team_member_has_template_no_go(
        db,
        planning_period_id=slot.planning_period_id,
        team_member_id=item.team_member_id,
        slot_date=slot.slot_date,
        shift_template_id=slot.shift_template_id,
    ):
        return "TEMPLATE_NO_GO"
    return None


def _same_as_before(row: RosterChangeSetItem) -> bool:
    return (
        row.before_team_member_id == row.after_team_member_id
        and row.before_manual_override == row.after_manual_override
        and row.before_comment == row.after_comment
    )


def _snapshot_matches(current: RosterSlotAssignment | None, expected: AssignmentSnapshot) -> bool:
    if expected.team_member_id is None:
        return current is None
    if current is None:
        return False
    return (
        current.team_member_id == expected.team_member_id
        and bool(current.manual_override) == expected.manual_override
        and current.comment == expected.comment
    )


def _refuse_if_expected_changed(
    db: Session,
    rows: list[RosterChangeSetItem],
    expected_current: dict[int, AssignmentSnapshot] | None,
) -> None:
    if not expected_current:
        return
    lock_roster_slots_for_assignment(db, list(expected_current))
    fresh = {
        row.roster_slot_id: row
        for row in db.scalars(
            select(RosterSlotAssignment)
            .where(RosterSlotAssignment.roster_slot_id.in_(list(expected_current)))
            .execution_options(populate_existing=True)
        )
    }
    for row in rows:
        if row.outcome != OUTCOME_APPLIED:
            continue
        expected = expected_current.get(row.roster_slot_id)
        if expected is None or _snapshot_matches(fresh.get(row.roster_slot_id), expected):
            continue
        row.outcome = OUTCOME_REFUSED
        row.refusal_code = "changed_since"
        row.findings = []


def _change_caused_error(warning: ValidationWarning, row: RosterChangeSetItem, slot: RosterSlot) -> bool:
    if warning.severity != "error":
        return False
    if row.after_team_member_id is not None and _warning_targets_slot(
        warning, slot_id=row.roster_slot_id, team_member_id=row.after_team_member_id
    ):
        return True
    if warning.code != "ROSTER_CONSTRAINT_COUPLED_SHIFT_REQUIRED":
        return False
    if warning.team_member_id is None or row.before_team_member_id != warning.team_member_id:
        return False
    if row.after_team_member_id == row.before_team_member_id:
        return False
    details = warning.details or {}
    partner_date = details.get("partner_date")
    if not isinstance(partner_date, str) or slot.shift_variant_id != details.get("paired_shift_variant_id"):
        return False
    return slot.slot_date.isoformat() == partner_date


def _any_target_group_published(
    db: Session,
    organization_id: int,
    planning_period_id: int,
    shift_group_id: int | None,
    slots: list[RosterSlot],
) -> bool:
    group_ids: set[int] = set()
    if shift_group_id is not None:
        group_ids.add(shift_group_id)
    for slot in slots:
        if slot.shift_template_id is not None:
            group_ids.update(shift_group_ids_for_template(db, slot.shift_template_id))
    for group_id in group_ids:
        status = get_shift_group_planning_status(
            db,
            planning_period_id=planning_period_id,
            shift_group_id=group_id,
            organization_id=organization_id,
        )
        if status is not None and not can_edit_planning_data(status.status):
            return True
    return False


def _evaluate_legal_subset(
    db: Session,
    organization_id: int,
    rows: list[RosterChangeSetItem],
    slots: dict[int, RosterSlot],
    mode: str,
) -> None:
    active = [row for row in rows if row.outcome == OUTCOME_APPLIED and row.roster_slot_id in slots]
    if not active:
        return
    for _pass in range(3):
        state = _overlay_rows(db, organization_id, active, slots)
        warnings = evaluate_plan_state(state, db=db)
        blocked: list[RosterChangeSetItem] = []
        for row in active:
            slot = slots[row.roster_slot_id]
            matched = [warning for warning in warnings if _change_caused_error(warning, row, slot)]
            if matched:
                row.findings = [_finding_json(warning) for warning in matched]
                row.outcome = OUTCOME_REFUSED
                row.refusal_code = "RULE_ERROR"
                blocked.append(row)
        if not blocked or mode == MODE_ALL_OR_NOTHING:
            _attach_non_blocking(rows, warnings)
            return
        active = [row for row in active if row not in blocked]
        if not active:
            return
    for row in active:
        if row.outcome == OUTCOME_APPLIED and row.after_team_member_id is not None:
            row.outcome = OUTCOME_REFUSED
            row.refusal_code = "UNSTABLE"
    _attach_non_blocking(rows, [])


def _overlay_rows(
    db: Session,
    organization_id: int,
    rows: list[RosterChangeSetItem],
    slots: dict[int, RosterSlot],
) -> object:
    dates = [slots[row.roster_slot_id].slot_date for row in rows]
    state = build_plan_state(
        db,
        organization_id=organization_id,
        start_date=min(dates) - COUPLED_SHIFT_WINDOW,
        end_date=max(dates) + COUPLED_SHIFT_WINDOW,
    )
    for row in rows:
        slot = slots[row.roster_slot_id]
        if row.after_team_member_id is None:
            state = overlay_clear_assignment(state, roster_slot_id=slot.id)
        else:
            state = overlay_candidate_assignment(
                state,
                slot=slot,
                team_member_id=row.after_team_member_id,
                assignment_id=None,
                manual_override=row.after_manual_override,
            )
    return state


def _attach_non_blocking(rows: list[RosterChangeSetItem], warnings: list[ValidationWarning]) -> None:
    for row in rows:
        if row.outcome != OUTCOME_APPLIED or row.after_team_member_id is None:
            continue
        matched = [
            warning
            for warning in warnings
            if warning.severity != "error"
            and _warning_targets_slot(warning, slot_id=row.roster_slot_id, team_member_id=row.after_team_member_id)
        ]
        if matched:
            row.findings = [_finding_json(warning) for warning in matched]


def _finding_json(warning: ValidationWarning) -> dict:
    return warning.model_dump(mode="json")


def _expected_predicates(slot_id: int, expected: AssignmentSnapshot) -> list:
    predicates = [
        RosterSlotAssignment.roster_slot_id == slot_id,
        RosterSlotAssignment.team_member_id == expected.team_member_id,
        RosterSlotAssignment.manual_override == expected.manual_override,
    ]
    if expected.comment is None:
        predicates.append(RosterSlotAssignment.comment.is_(None))
    else:
        predicates.append(RosterSlotAssignment.comment == expected.comment)
    return predicates


def _write_expected_row(
    db: Session,
    *,
    organization_id: int,
    actor: str,
    source: str,
    row: RosterChangeSetItem,
    expected: AssignmentSnapshot,
) -> bool:
    slot_id = row.roster_slot_id
    if expected.team_member_id is None:
        existing = db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot_id))
        if existing is not None or row.after_team_member_id is None:
            return existing is None and row.after_team_member_id is None
        try:
            with db.begin_nested():
                upsert_roster_slot_assignment(
                    db,
                    RosterSlotAssignmentUpsert(
                        roster_slot_id=slot_id,
                        team_member_id=row.after_team_member_id,
                        comment=row.after_comment,
                        manual_override=row.after_manual_override,
                    ),
                    organization_id=organization_id,
                    actor=actor,
                    source=source,
                    commit=False,
                    enforce_preflight=False,
                )
        except IntegrityError:
            return False
        return True
    predicates = _expected_predicates(slot_id, expected)
    if row.after_team_member_id is None:
        existing = db.scalar(select(RosterSlotAssignment).where(*predicates))
        if existing is None:
            return False
        assignment_id = existing.id
        result = db.execute(delete(RosterSlotAssignment).where(*predicates))
        if result.rowcount != 1:
            return False
        record_audit(
            db,
            actor=actor,
            source=source,
            action="delete",
            entity_type="roster_slot_assignment",
            entity_id=assignment_id,
            details={"roster_slot_id": slot_id},
        )
        return True
    result = db.execute(
        update(RosterSlotAssignment)
        .where(*predicates)
        .values(
            team_member_id=row.after_team_member_id,
            comment=row.after_comment,
            manual_override=row.after_manual_override,
            source=source,
        )
    )
    if result.rowcount != 1:
        return False
    assignment = db.scalar(select(RosterSlotAssignment).where(RosterSlotAssignment.roster_slot_id == slot_id))
    if assignment is None:
        return False
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="roster_slot_assignment",
        entity_id=assignment.id,
        details={
            "roster_slot_id": slot_id,
            "team_member_id": row.after_team_member_id,
        },
    )
    return True


def _write_rows(
    db: Session,
    organization_id: int,
    actor: str,
    source: str,
    rows: list[RosterChangeSetItem],
    slots: dict[int, RosterSlot],
    *,
    mode: str,
    expected_current: dict[int, AssignmentSnapshot] | None,
) -> None:
    nested = db.begin_nested() if expected_current else None
    failed_slots: list[int] = []
    for row in rows:
        if row.outcome != OUTCOME_APPLIED or row.roster_slot_id not in slots:
            continue
        expected = expected_current.get(row.roster_slot_id) if expected_current else None
        if expected is not None:
            if not _write_expected_row(
                db,
                organization_id=organization_id,
                actor=actor,
                source=source,
                row=row,
                expected=expected,
            ):
                failed_slots.append(row.roster_slot_id)
            continue
        if row.after_team_member_id is None:
            clear_roster_slot_assignment(
                db,
                RosterSlotAssignmentClear(roster_slot_id=row.roster_slot_id),
                organization_id=organization_id,
                actor=actor,
                source=source,
                commit=False,
            )
        else:
            upsert_roster_slot_assignment(
                db,
                RosterSlotAssignmentUpsert(
                    roster_slot_id=row.roster_slot_id,
                    team_member_id=row.after_team_member_id,
                    comment=row.after_comment,
                    manual_override=row.after_manual_override,
                ),
                organization_id=organization_id,
                actor=actor,
                source=source,
                commit=False,
                enforce_preflight=False,
            )
    if nested is None:
        return
    if failed_slots and mode == MODE_ALL_OR_NOTHING:
        nested.rollback()
        failed = set(failed_slots)
        for row in rows:
            if row.roster_slot_id in failed:
                row.outcome = OUTCOME_REFUSED
                row.refusal_code = "changed_since"
                row.findings = []
            elif row.outcome == OUTCOME_APPLIED:
                row.outcome = OUTCOME_REFUSED
                row.refusal_code = row.refusal_code or "SET_REFUSED"
        return
    nested.commit()
    for row in rows:
        if row.roster_slot_id in failed_slots:
            row.outcome = OUTCOME_REFUSED
            row.refusal_code = "changed_since"
            row.findings = []
