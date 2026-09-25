from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.schemas.domain import ValidationWarning
from app.services.rules.protocol import Rule
from app.services.rules.state import PlanState

_RULES: list[Rule] = []


def register_rule(rule: Rule) -> None:
    _RULES.append(rule)


def clear_rules() -> None:
    _RULES.clear()


def _roster_rules() -> tuple[Rule, ...]:
    from app.services.rules.builtin import builtin_roster_rules
    from app.services.rules.member_patterns import member_pattern_rules
    from app.services.rules.shift_constraints import shift_constraint_rules

    return shift_constraint_rules() + member_pattern_rules() + builtin_roster_rules()


def _statutory_rules(organization_id: int, db: Any | None) -> tuple[Rule, ...]:
    from app.services.rules.statutory import statutory_rules_for_org

    return statutory_rules_for_org(db, organization_id) if db is not None else ()


def resolve_active_rules(
    organization_id: int,
    start_date: date,
    end_date: date,
    db: Any | None = None,
) -> tuple[Rule, ...]:
    del start_date, end_date
    return _roster_rules() + _statutory_rules(organization_id, db) + tuple(_RULES)


def _evaluate_rule(rule: Rule, state: PlanState, db: Any | None) -> list[ValidationWarning]:
    from app.services.rules.member_patterns import MemberPlanningPatternsRule

    if isinstance(rule, MemberPlanningPatternsRule) and db is not None:
        return MemberPlanningPatternsRule(db=db).evaluate(state)
    return rule.evaluate(state)


def evaluate_plan_state(
    state: PlanState,
    *,
    db: Any | None = None,
    statutory_state: PlanState | None = None,
) -> list[ValidationWarning]:
    """Run every active rule on ``state``.

    With ``statutory_state`` the statutory working-time rules, which are about the person and
    not the shift group, run on that state instead. Roster rules stay on ``state``, whose cells
    and intents belong to the same group as its assignments.
    """
    if statutory_state is None:
        warnings: list[ValidationWarning] = []
        for rule in resolve_active_rules(state.organization_id, state.start_date, state.end_date, db=db):
            warnings.extend(_evaluate_rule(rule, state, db))
        return warnings
    warnings = []
    for rule in _roster_rules():
        warnings.extend(_evaluate_rule(rule, state, db))
    for rule in _statutory_rules(state.organization_id, db):
        warnings.extend(_evaluate_rule(rule, statutory_state, db))
    for rule in _RULES:
        warnings.extend(_evaluate_rule(rule, state, db))
    return warnings


def roster_lookback_for(rule: Rule) -> timedelta:
    return getattr(rule, "roster_lookback", rule.lookback)


def max_lookback(rules: Sequence[Rule]) -> timedelta:
    if not rules:
        return timedelta(0)
    return max(rule.lookback for rule in rules)


def max_roster_lookback(rules: Sequence[Rule]) -> timedelta:
    if not rules:
        return timedelta(0)
    return max(roster_lookback_for(rule) for rule in rules)
