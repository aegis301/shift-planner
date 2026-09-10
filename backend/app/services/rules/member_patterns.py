from datetime import timedelta

from sqlalchemy.orm import Session

from app.models import TeamMemberPlanningPattern
from app.schemas.domain import ValidationWarning
from app.services.member_planning_patterns import evaluate_member_planning_patterns
from app.services.rules.builtin import ordered_assignments
from app.services.rules.state import PlanState


class _VariantOnlySession:
    def get(self, model, ident):
        del model, ident
        return None


class MemberPlanningPatternsRule:
    code = "MEMBER_PATTERN"
    severity = "info"
    lookback = timedelta(0)

    def __init__(self, db: Session | None = None) -> None:
        self._db = db

    def evaluate(self, state: PlanState) -> list[ValidationWarning]:
        session = self._db if self._db is not None else _VariantOnlySession()
        warnings: list[ValidationWarning] = []
        for assignment in ordered_assignments(state):
            slot = assignment.roster_slot
            if slot is None or not (state.start_date <= slot.slot_date <= state.end_date):
                continue
            patterns = _ordered_patterns(state.patterns_by_member_id.get(assignment.team_member_id, ()))
            if not patterns:
                continue
            warnings.extend(
                evaluate_member_planning_patterns(
                    db=session,
                    slot=slot,
                    team_member_id=assignment.team_member_id,
                    patterns=patterns,
                    assignment_id=assignment.id if assignment.id > 0 else None,
                )
            )
        return warnings


def _ordered_patterns(rows: tuple[TeamMemberPlanningPattern, ...] | list[TeamMemberPlanningPattern]) -> list[TeamMemberPlanningPattern]:
    return sorted(rows, key=lambda item: (item.display_order, item.id))


def member_pattern_rules() -> tuple[MemberPlanningPatternsRule]:
    return (MemberPlanningPatternsRule(),)
