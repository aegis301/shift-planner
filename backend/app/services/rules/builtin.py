from collections import defaultdict
from datetime import date, timedelta

from app.models import RosterSlotAssignment
from app.schemas.domain import ValidationWarning
from app.services.rules.state import PlanState


def ordered_assignments(state: PlanState) -> list[RosterSlotAssignment]:
    rows = [row for row in state.assignments_by_id.values() if row.roster_slot is not None]
    return sorted(
        rows,
        key=lambda row: (
            row.roster_slot.slot_date,
            row.roster_slot.position,
            row.roster_slot.shift_template_id or 0,
            row.roster_slot.shift_variant_id or 0,
            row.id,
        ),
    )


def _in_requested_window(slot_date: date, state: PlanState) -> bool:
    return state.start_date <= slot_date <= state.end_date


def _weekend_anchor(slot_date: date) -> date | None:
    weekday = slot_date.weekday()
    if weekday == 5:
        return slot_date
    if weekday == 6:
        return slot_date - timedelta(days=1)
    return None


def _saturday_touches_window(saturday: date, start: date, end: date) -> bool:
    sunday = saturday + timedelta(days=1)
    return saturday <= end and sunday >= start


class TemplateNoGoConflictRule:
    code = "ROSTER_TEMPLATE_NO_GO_CONFLICT"
    severity = "error"
    lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        no_gos = [intent for intent in state.shift_intents if intent.kind == "no_go"]
        warnings: list[ValidationWarning] = []
        for assignment in ordered_assignments(state):
            if not _in_requested_window(assignment.roster_slot.slot_date, state):
                continue
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
        return warnings


class DuplicateDayRule:
    code = "ROSTER_MATRIX_DUPLICATE_DAY"
    severity = "warning"
    lookback = timedelta(0)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        grouped: dict[tuple[int, date], list[RosterSlotAssignment]] = {}
        order: list[tuple[int, date]] = []
        for assignment in ordered_assignments(state):
            slot_date = assignment.roster_slot.slot_date
            if not _in_requested_window(slot_date, state):
                continue
            key = (assignment.team_member_id, slot_date)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(assignment)
        warnings: list[ValidationWarning] = []
        for key in order:
            day_assignments = grouped[key]
            if len(day_assignments) < 2:
                continue
            team_member_id, assignment_date = key
            warnings.append(
                ValidationWarning(
                    code="ROSTER_MATRIX_DUPLICATE_DAY",
                    severity="warning",
                    message="Team member is assigned to more than one final roster slot on the same day.",
                    team_member_id=team_member_id,
                    date=assignment_date,
                    details={
                        "roster_slot_ids": [row.roster_slot_id for row in day_assignments],
                        "count": len(day_assignments),
                    },
                )
            )
        return warnings


class ConsecutiveWeekendsRule:
    code = "ROSTER_CONSECUTIVE_WEEKENDS"
    severity = "warning"
    lookback = timedelta(days=7)

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        anchors_by_member: dict[int, set[date]] = defaultdict(set)
        slots_by_member_anchor: dict[tuple[int, date], list[int]] = defaultdict(list)
        member_order: list[int] = []
        for assignment in ordered_assignments(state):
            slot = assignment.roster_slot
            anchor = _weekend_anchor(slot.slot_date)
            if anchor is None:
                continue
            if assignment.team_member_id not in anchors_by_member:
                member_order.append(assignment.team_member_id)
            anchors_by_member[assignment.team_member_id].add(anchor)
            slots_by_member_anchor[(assignment.team_member_id, anchor)].append(slot.id)
        warnings: list[ValidationWarning] = []
        for member_id in member_order:
            ordered = sorted(anchors_by_member[member_id])
            pairs = [
                (ordered[i], ordered[i + 1])
                for i in range(len(ordered) - 1)
                if ordered[i + 1] - ordered[i] == timedelta(days=7)
            ]
            pairs = [
                pair
                for pair in pairs
                if _saturday_touches_window(pair[0], state.start_date, state.end_date)
                or _saturday_touches_window(pair[1], state.start_date, state.end_date)
            ]
            if not pairs:
                continue
            slot_ids: set[int] = set()
            for sat_a, sat_b in pairs:
                slot_ids.update(slots_by_member_anchor.get((member_id, sat_a), []))
                slot_ids.update(slots_by_member_anchor.get((member_id, sat_b), []))
            warnings.append(
                ValidationWarning(
                    code="ROSTER_CONSECUTIVE_WEEKENDS",
                    severity="warning",
                    message="Team member is assigned on two consecutive calendar weekends.",
                    team_member_id=member_id,
                    date=None,
                    details={
                        "pairs": [
                            {
                                "first_weekend_saturday": first.isoformat(),
                                "second_weekend_saturday": second.isoformat(),
                            }
                            for first, second in pairs
                        ],
                        "roster_slot_ids": sorted(slot_ids),
                    },
                )
            )
        return warnings


def builtin_roster_rules() -> tuple[TemplateNoGoConflictRule, DuplicateDayRule, ConsecutiveWeekendsRule]:
    return (
        TemplateNoGoConflictRule(),
        DuplicateDayRule(),
        ConsecutiveWeekendsRule(),
    )
