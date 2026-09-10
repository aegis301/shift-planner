from collections.abc import Sequence
from datetime import date, timedelta

from app.services.rules.protocol import Rule

_RULES: list[Rule] = []


def register_rule(rule: Rule) -> None:
    _RULES.append(rule)


def clear_rules() -> None:
    _RULES.clear()


def resolve_active_rules(
    organization_id: int,
    start_date: date,
    end_date: date,
) -> tuple[Rule, ...]:
    del organization_id, start_date, end_date
    from app.services.rules.builtin import builtin_roster_rules
    from app.services.rules.member_patterns import member_pattern_rules
    from app.services.rules.shift_constraints import shift_constraint_rules

    return shift_constraint_rules() + member_pattern_rules() + builtin_roster_rules() + tuple(_RULES)


def max_lookback(rules: Sequence[Rule]) -> timedelta:
    if not rules:
        return timedelta(0)
    return max(rule.lookback for rule in rules)
