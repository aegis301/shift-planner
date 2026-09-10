from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.schemas import ContractCategoryRule
from app.services.holidays import classify_day

RUFDIENST = "rufdienst"


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, ContractCategoryRule):
        return value.model_dump()
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return dict(value)
    return None


def _interval_minutes(started_at: datetime | None, ended_at: datetime | None) -> int:
    if started_at is None or ended_at is None:
        return 0
    delta = ended_at - started_at
    return max(0, int(delta.total_seconds() // 60))


def _episode_minutes(episodes: Sequence[Any] | None) -> int:
    total = 0
    for episode in episodes or ():
        mapping = episode if isinstance(episode, dict) else None
        duration = mapping.get("duration_minutes") if mapping is not None else getattr(episode, "duration_minutes", None)
        if duration is not None:
            total += max(0, int(duration))
            continue
        started = mapping.get("started_at") if mapping is not None else getattr(episode, "started_at", None)
        ended = mapping.get("ended_at") if mapping is not None else getattr(episode, "ended_at", None)
        total += _interval_minutes(started, ended)
    return total


def _scale(minutes: int, factor: Decimal) -> int:
    if minutes <= 0 or factor <= 0:
        return 0
    return int((Decimal(minutes) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _slot_is_holiday(slot: Any, day_class: str) -> bool:
    slot_date = getattr(slot, "slot_date", None)
    if isinstance(slot_date, date):
        return classify_day(slot_date) == "holiday"
    return day_class == "holiday"


def resolve_valuation_rule(*, contract_group: Any, template: Any) -> ContractCategoryRule:
    category = getattr(template, "category", "other")
    override = _as_mapping(getattr(template, "valuation_override", None))
    if override:
        if not override.get("category"):
            override["category"] = category
        return ContractCategoryRule.model_validate(override)
    for raw in getattr(contract_group, "category_rules", None) or []:
        rule = ContractCategoryRule.model_validate(raw)
        if rule.category == category:
            return rule
    return ContractCategoryRule(
        category=category,
        credit_mode="duration",
        statutory_factor=Decimal("1"),
    )


def _effective_credit_factor(rule: ContractCategoryRule, *, holiday: bool) -> Decimal:
    bonus = (rule.holiday_credit_bonus / Decimal("100")) if holiday else Decimal("0")
    if rule.credit_mode == "factor":
        return (rule.credit_factor or Decimal("0")) + bonus
    if rule.credit_mode == "duration":
        return Decimal("1") + bonus
    return Decimal("0")


def statutory_work_minutes(
    *,
    slot: Any,
    contract_group: Any,
    template: Any,
    day_class: str,
    episodes: Sequence[Any] | None,
) -> int:
    del day_class
    rule = resolve_valuation_rule(contract_group=contract_group, template=template)
    duty = _interval_minutes(getattr(slot, "starts_at", None), getattr(slot, "ends_at", None))
    episode = _episode_minutes(episodes)
    category = getattr(template, "category", None)
    if category == RUFDIENST:
        return _scale(episode, rule.statutory_factor)
    extra = episode if rule.call_outs_count_as_work else 0
    return _scale(duty, rule.statutory_factor) + extra


def tariff_credit_minutes(
    *,
    slot: Any,
    contract_group: Any,
    template: Any,
    day_class: str,
    episodes: Sequence[Any] | None,
) -> int:
    rule = resolve_valuation_rule(contract_group=contract_group, template=template)
    duty = _interval_minutes(getattr(slot, "starts_at", None), getattr(slot, "ends_at", None))
    episode = _episode_minutes(episodes)
    holiday = _slot_is_holiday(slot, day_class)
    duty_credit = _scale(duty, _effective_credit_factor(rule, holiday=holiday))
    extra = episode if rule.call_outs_count_as_work else 0
    return duty_credit + extra
