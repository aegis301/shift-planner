from __future__ import annotations

from calendar import monthrange
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlanningPeriod,
    PlanningPlanVersion,
    TeamMember,
    WorkTimeConsent,
    WorkTimeRuleSet,
)
from app.schemas import (
    WorkTimeConsentCreate,
    WorkTimeConsentPlanFinding,
    WorkTimeConsentRead,
    WorkTimeConsentRevoke,
    WorkTimeRule,
    WorkTimeRuleOptOutWeeklyCap,
    WorkTimeRuleWeeklyAverageCap,
)
from app.services.audit import record_audit
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group

_RULES_ADAPTER = TypeAdapter(list[WorkTimeRule])


def add_calendar_months(value: date, months: int) -> date:
    year = value.year
    month = value.month + months
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def derive_effective_until(*, revoked_at: date | None, notice_period_months: int) -> date | None:
    if revoked_at is None:
        return None
    return add_calendar_months(revoked_at, notice_period_months)


def work_time_consent_to_read(row: WorkTimeConsent) -> WorkTimeConsentRead:
    return WorkTimeConsentRead.model_validate(row)


def _require_member(db: Session, team_member_id: int, organization_id: int) -> TeamMember:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        raise ValueError("Team member not found")
    return member


def list_work_time_consents(db: Session, team_member_id: int, *, organization_id: int) -> list[WorkTimeConsent]:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != organization_id:
        return []
    return list(
        db.scalars(
            select(WorkTimeConsent)
            .where(
                WorkTimeConsent.organization_id == organization_id,
                WorkTimeConsent.team_member_id == team_member_id,
            )
            .order_by(WorkTimeConsent.valid_from.desc(), WorkTimeConsent.id.desc())
        )
    )


def load_work_time_consents_for_members(
    db: Session,
    *,
    organization_id: int,
    team_member_ids: set[int],
) -> dict[int, tuple[WorkTimeConsent, ...]]:
    if not team_member_ids:
        return {}
    rows = list(
        db.scalars(
            select(WorkTimeConsent).where(
                WorkTimeConsent.organization_id == organization_id,
                WorkTimeConsent.team_member_id.in_(team_member_ids),
            )
        )
    )
    grouped: dict[int, list[WorkTimeConsent]] = {}
    for row in rows:
        grouped.setdefault(row.team_member_id, []).append(row)
    return {member_id: tuple(items) for member_id, items in grouped.items()}


def record_work_time_consent(
    db: Session,
    team_member_id: int,
    payload: WorkTimeConsentCreate,
    *,
    organization_id: int,
    recorded_by_user_id: int | None,
    actor: str,
    source: str,
) -> WorkTimeConsent:
    _require_member(db, team_member_id, organization_id)
    row = WorkTimeConsent(
        organization_id=organization_id,
        team_member_id=team_member_id,
        consent_type=payload.consent_type,
        tier=payload.tier.strip(),
        valid_from=payload.valid_from,
        signed_document_reference=payload.signed_document_reference,
        recorded_by_user_id=recorded_by_user_id,
        notice_period_months=payload.notice_period_months,
        revoked_at=None,
        effective_until=None,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="create",
        entity_type="work_time_consent",
        entity_id=row.id,
        details={"team_member_id": team_member_id, "tier": row.tier},
    )
    db.commit()
    db.refresh(row)
    return row


def _opt_out_rule(rule_set: WorkTimeRuleSet | WorkTimeRuleOptOutWeeklyCap | Sequence[object]) -> WorkTimeRuleOptOutWeeklyCap | None:
    if isinstance(rule_set, WorkTimeRuleOptOutWeeklyCap):
        return rule_set
    raw = rule_set.rules if isinstance(rule_set, WorkTimeRuleSet) else list(rule_set)
    for item in _RULES_ADAPTER.validate_python(raw or []):
        if isinstance(item, WorkTimeRuleOptOutWeeklyCap):
            return item
    return None


def _base_cap_hours(rule: WorkTimeRuleOptOutWeeklyCap) -> Decimal:
    tiers = dict(rule.hours_by_tier)
    if "standard" in tiers:
        return tiers["standard"]
    without_regional = {key: value for key, value in tiers.items() if key != "regional_agreement"}
    values = list(without_regional.values() or tiers.values())
    return min(values)


def consent_effective_on(row: WorkTimeConsent, on_date: date) -> bool:
    if row.valid_from > on_date:
        return False
    until = row.effective_until
    if until is None and row.revoked_at is not None:
        until = derive_effective_until(revoked_at=row.revoked_at, notice_period_months=row.notice_period_months)
    return until is None or on_date <= until


def _consent_on_date(consents: Sequence[WorkTimeConsent], on_date: date) -> WorkTimeConsent | None:
    eligible = [row for row in consents if consent_effective_on(row, on_date)]
    if not eligible:
        return None
    eligible.sort(key=lambda row: (row.valid_from, row.id), reverse=True)
    return eligible[0]


def applicable_weekly_cap(
    member_id: int,
    on_date: date,
    rule_set: WorkTimeRuleSet | WorkTimeRuleOptOutWeeklyCap | Sequence[object],
    consents: Sequence[WorkTimeConsent] | None = None,
    *,
    db: Session | None = None,
) -> Decimal:
    rule = _opt_out_rule(rule_set)
    if rule is None:
        if isinstance(rule_set, WorkTimeRuleSet):
            for item in _RULES_ADAPTER.validate_python(rule_set.rules or []):
                if isinstance(item, WorkTimeRuleWeeklyAverageCap):
                    return item.hours
        return Decimal("48")
    base = _base_cap_hours(rule)
    records = list(consents) if consents is not None else []
    if consents is None and db is not None:
        records = list(
            db.scalars(select(WorkTimeConsent).where(WorkTimeConsent.team_member_id == member_id))
        )
    chosen = _consent_on_date(records, on_date)
    if chosen is None:
        return base
    hours = rule.hours_by_tier.get(chosen.tier)
    if hours is None:
        return base
    return hours


def scan_future_published_plan_findings(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    as_of: date,
) -> list[WorkTimeConsentPlanFinding]:
    from app.services.validation import validate_roster

    versions = list(
        db.scalars(
            select(PlanningPlanVersion)
            .join(PlanningPeriod, PlanningPeriod.id == PlanningPlanVersion.planning_period_id)
            .where(
                PlanningPlanVersion.organization_id == organization_id,
                PlanningPlanVersion.lifecycle_phase == "published",
            )
            .order_by(PlanningPeriod.year, PlanningPeriod.month, PlanningPlanVersion.id)
        )
    )
    findings: list[WorkTimeConsentPlanFinding] = []
    seen: set[tuple[int, int]] = set()
    for version in versions:
        period = version.planning_period or db.get(PlanningPeriod, version.planning_period_id)
        if period is None:
            continue
        last_day = date(period.year, period.month, monthrange(period.year, period.month)[1])
        if last_day < as_of:
            continue
        key = (version.planning_period_id, version.shift_group_id)
        if key in seen:
            continue
        roster = team_member_ids_for_period_shift_group(
            db, planning_period_id=version.planning_period_id, shift_group_id=version.shift_group_id
        )
        if team_member_id not in roster:
            continue
        seen.add(key)
        warnings = validate_roster(
            db,
            version.planning_period_id,
            organization_id=organization_id,
            shift_group_id=version.shift_group_id,
        )
        relevant = [
            warning
            for warning in warnings
            if warning.team_member_id == team_member_id
            and warning.code in {"WORKTIME_WEEKLY_AVERAGE_OPT_OUT", "WORKTIME_WEEKLY_AVERAGE"}
        ]
        if not relevant:
            continue
        findings.append(
            WorkTimeConsentPlanFinding(
                planning_plan_version_id=version.id,
                planning_period_id=version.planning_period_id,
                year=period.year,
                month=period.month,
                shift_group_id=version.shift_group_id,
                warning_codes=sorted({item.code for item in relevant}),
            )
        )
    return findings


def revoke_work_time_consent(
    db: Session,
    consent_id: int,
    payload: WorkTimeConsentRevoke,
    *,
    organization_id: int,
    actor: str,
    source: str,
) -> tuple[WorkTimeConsent, list[WorkTimeConsentPlanFinding]]:
    row = db.get(WorkTimeConsent, consent_id)
    if row is None or row.organization_id != organization_id:
        raise ValueError("Consent record not found")
    if row.revoked_at is not None:
        raise ValueError("Consent record is immutable once revoked")
    revoked_at = payload.revoked_at or date.today()
    if payload.notice_period_months is not None:
        row.notice_period_months = payload.notice_period_months
    row.revoked_at = revoked_at
    row.effective_until = derive_effective_until(
        revoked_at=revoked_at, notice_period_months=row.notice_period_months
    )
    db.flush()
    findings = scan_future_published_plan_findings(
        db,
        team_member_id=row.team_member_id,
        organization_id=organization_id,
        as_of=revoked_at,
    )
    record_audit(
        db,
        actor=actor,
        source=source,
        action="revoke",
        entity_type="work_time_consent",
        entity_id=row.id,
        details={
            "revoked_at": revoked_at.isoformat(),
            "effective_until": row.effective_until.isoformat() if row.effective_until else None,
            "affected_plan_count": len(findings),
        },
    )
    db.commit()
    db.refresh(row)
    return row, findings
