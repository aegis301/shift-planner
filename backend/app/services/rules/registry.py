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


def resolve_active_rules(
    organization_id: int,
    start_date: date,
    end_date: date,
    db: Any | None = None,
) -> tuple[Rule, ...]:
    del start_date, end_date
    from app.services.rules.builtin import builtin_roster_rules
    from app.services.rules.member_patterns import member_pattern_rules
    from app.services.rules.shift_constraints import shift_constraint_rules
    from app.services.rules.statutory import statutory_rules_for_org

    statutory = statutory_rules_for_org(db, organization_id) if db is not None else ()
    return shift_constraint_rules() + member_pattern_rules() + builtin_roster_rules() + statutory + tuple(_RULES)


def evaluate_plan_state(state: PlanState, *, db: Any | None = None) -> list[ValidationWarning]:
    from app.services.rules.member_patterns import MemberPlanningPatternsRule

    warnings: list[ValidationWarning] = []
    for rule in resolve_active_rules(state.organization_id, state.start_date, state.end_date, db=db):
        if isinstance(rule, MemberPlanningPatternsRule) and db is not None:
            warnings.extend(MemberPlanningPatternsRule(db=db).evaluate(state))
        else:
            warnings.extend(rule.evaluate(state))
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
