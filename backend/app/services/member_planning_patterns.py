from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Organization, RosterSlot, ShiftVariant, TeamMember, TeamMemberPlanningPattern
from app.schemas import (
    AvoidTimeWindowBand,
    AvoidTimeWindowMemberPatternRule,
    AllowedCalendarWeekParityMemberPatternRule,
    MemberPlanningPatternRule,
    OrganizationMemberPatternPolicy,
    RecurringWeekdayStatusMemberPatternRule,
    TeamMemberPlanningPatternRead,
    TeamMemberPlanningPatternsReplace,
    ValidationWarning,
)
from app.services.audit import record_audit
from app.services.tenancy import require_team_member_in_org

PatternWeekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

_WEEKDAY_TO_INDEX: dict[PatternWeekday, int] = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


@dataclass(frozen=True)
class ResolvedMemberPattern:
    pattern_id: int
    label: str
    severity: str
    rule: AvoidTimeWindowMemberPatternRule | AllowedCalendarWeekParityMemberPatternRule | RecurringWeekdayStatusMemberPatternRule


def default_member_pattern_policy() -> OrganizationMemberPatternPolicy:
    return OrganizationMemberPatternPolicy()


def read_organization_member_pattern_policy(organization: Organization) -> OrganizationMemberPatternPolicy:
    raw = organization.member_pattern_policy or {}
    return OrganizationMemberPatternPolicy.model_validate(raw)


def update_organization_member_pattern_policy(
    db: Session,
    organization: Organization,
    *,
    policy: OrganizationMemberPatternPolicy,
    actor: str,
    source: str,
) -> OrganizationMemberPatternPolicy:
    normalized = OrganizationMemberPatternPolicy.model_validate(policy.model_dump())
    organization.member_pattern_policy = normalized.model_dump()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="update",
        entity_type="organization_member_pattern_policy",
        entity_id=organization.id,
        details={"hard_types": normalized.hard_types},
    )
    db.commit()
    db.refresh(organization)
    return read_organization_member_pattern_policy(organization)


def _parse_rule(
    raw: dict,
) -> AvoidTimeWindowMemberPatternRule | AllowedCalendarWeekParityMemberPatternRule | RecurringWeekdayStatusMemberPatternRule:
    rule_type = raw.get("type")
    if rule_type == "avoid_time_window":
        return AvoidTimeWindowMemberPatternRule.model_validate(raw)
    if rule_type == "allowed_calendar_week_parity":
        return AllowedCalendarWeekParityMemberPatternRule.model_validate(raw)
    if rule_type == "recurring_weekday_status":
        return RecurringWeekdayStatusMemberPatternRule.model_validate(raw)
    raise ValueError("Unsupported member planning pattern rule type")


def effective_pattern_severity(rule: MemberPlanningPatternRule, severity: str) -> str:
    if rule.type in ("avoid_time_window", "recurring_weekday_status"):
        return "info"
    return severity


def validate_pattern_severity(
    rule: MemberPlanningPatternRule,
    *,
    severity: str,
    policy: OrganizationMemberPatternPolicy,
) -> None:
    effective = effective_pattern_severity(rule, severity)
    if effective == "error" and rule.type not in policy.hard_types:
        raise ValueError("error severity is not allowed for this pattern type in the organization policy")


def list_team_member_planning_patterns(
    db: Session, *, team_member_id: int, organization_id: int, active_only: bool = False
) -> list[TeamMemberPlanningPattern]:
    require_team_member_in_org(db, team_member_id, organization_id)
    stmt = (
        select(TeamMemberPlanningPattern)
        .where(
            TeamMemberPlanningPattern.team_member_id == team_member_id,
            TeamMemberPlanningPattern.organization_id == organization_id,
        )
        .order_by(TeamMemberPlanningPattern.display_order, TeamMemberPlanningPattern.id)
    )
    if active_only:
        stmt = stmt.where(TeamMemberPlanningPattern.is_active.is_(True))
    return list(db.scalars(stmt))


def merge_recurring_pattern_cell_target(cell_date: date, patterns: list[TeamMemberPlanningPattern]) -> str | None:
    sorted_rows = sorted(patterns, key=lambda r: (r.display_order, r.id))
    target: str | None = None
    for row in sorted_rows:
        if not row.is_active:
            continue
        rule = _parse_rule(row.rule)
        if rule.type == "recurring_weekday_status":
            wd_key = _weekday_code(cell_date)
            if wd_key in rule.weekdays:
                target = rule.status
        elif rule.type == "allowed_calendar_week_parity":
            _, iso_week, _ = cell_date.isocalendar()
            actual_parity: Literal["even", "odd"] = "even" if iso_week % 2 == 0 else "odd"
            if actual_parity != rule.parity:
                target = rule.status
    return target


def sync_recurring_weekday_status_all_open_periods_for_member(
    db: Session, *, team_member_id: int, organization_id: int, actor: str, source: str
) -> None:
    from app.services.matrix import sync_recurring_weekday_cells_for_member_open_periods

    patterns = list_team_member_planning_patterns(db, team_member_id=team_member_id, organization_id=organization_id)
    sync_recurring_weekday_cells_for_member_open_periods(
        db,
        team_member_id=team_member_id,
        organization_id=organization_id,
        patterns=patterns,
        actor=actor,
        source=source,
    )


def sync_recurring_weekday_for_new_period(
    db: Session, *, planning_period_id: int, organization_id: int, actor: str, source: str
) -> None:
    from app.services.matrix import apply_recurring_weekday_status_to_one_period

    members = list(
        db.scalars(
            select(TeamMember).where(
                TeamMember.organization_id == organization_id,
                TeamMember.is_active.is_(True),
            )
        )
    )
    for member in members:
        patterns = list_team_member_planning_patterns(db, team_member_id=member.id, organization_id=organization_id)
        apply_recurring_weekday_status_to_one_period(
            db,
            planning_period_id=planning_period_id,
            team_member_id=member.id,
            organization_id=organization_id,
            patterns=patterns,
            actor=actor,
            source=source,
        )
    db.commit()


def replace_team_member_planning_patterns(
    db: Session,
    *,
    team_member_id: int,
    organization_id: int,
    payload: TeamMemberPlanningPatternsReplace,
    policy: OrganizationMemberPatternPolicy,
    actor: str,
    source: str,
) -> list[TeamMemberPlanningPattern]:
    require_team_member_in_org(db, team_member_id, organization_id)
    for item in payload.patterns:
        validate_pattern_severity(item.rule, severity=item.severity, policy=policy)
    existing = list(
        db.scalars(
            select(TeamMemberPlanningPattern).where(
                TeamMemberPlanningPattern.team_member_id == team_member_id,
                TeamMemberPlanningPattern.organization_id == organization_id,
            )
        )
    )
    for row in existing:
        db.delete(row)
    db.flush()
    created: list[TeamMemberPlanningPattern] = []
    for index, item in enumerate(payload.patterns):
        row = TeamMemberPlanningPattern(
            organization_id=organization_id,
            team_member_id=team_member_id,
            label=item.label.strip(),
            is_active=item.is_active,
            rule=item.rule.model_dump(mode="json"),
            severity=effective_pattern_severity(item.rule, item.severity),
            display_order=item.display_order if item.display_order else index,
        )
        db.add(row)
        created.append(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        source=source,
        action="replace",
        entity_type="team_member_planning_patterns",
        entity_id=team_member_id,
        details={"count": len(created)},
    )
    db.commit()
    for row in created:
        db.refresh(row)
    sync_recurring_weekday_status_all_open_periods_for_member(
        db, team_member_id=team_member_id, organization_id=organization_id, actor=actor, source=source
    )
    return created


def pattern_to_read(row: TeamMemberPlanningPattern) -> TeamMemberPlanningPatternRead:
    return TeamMemberPlanningPatternRead.model_validate(row)


def _weekday_code(day: date) -> PatternWeekday:
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day.weekday()]


def _resolve_slot_interval(db: Session, slot: RosterSlot) -> tuple[datetime, datetime] | None:
    if slot.starts_at is not None and slot.ends_at is not None:
        return slot.starts_at, slot.ends_at
    variant: ShiftVariant | None = slot.shift_variant
    if variant is None and slot.shift_variant_id is not None:
        variant = db.get(ShiftVariant, slot.shift_variant_id)
    if variant is None:
        return None
    start = datetime.combine(slot.slot_date, variant.starts_at)
    end_date = slot.slot_date + timedelta(days=variant.end_day_offset)
    end = datetime.combine(end_date, variant.ends_at)
    if end <= start:
        end = end + timedelta(days=1)
    return start, end


def _window_interval_for_day(
    day: date, window_start: time, window_end: time, *, tz: datetime.tzinfo | None = None
) -> tuple[datetime, datetime]:
    if tz is None:
        start = datetime.combine(day, window_start)
        if window_end <= window_start:
            end = datetime.combine(day + timedelta(days=1), window_end)
        else:
            end = datetime.combine(day, window_end)
        return start, end
    start = datetime.combine(day, window_start, tzinfo=tz)
    if window_end <= window_start:
        end = datetime.combine(day + timedelta(days=1), window_end, tzinfo=tz)
    else:
        end = datetime.combine(day, window_end, tzinfo=tz)
    return start, end


def _intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def _days_for_anchor(
    *,
    slot: RosterSlot,
    shift_start: datetime,
    shift_end: datetime,
    anchor: Literal["slot_start_day", "any_overlap_day"],
) -> list[date]:
    if anchor == "slot_start_day":
        return [slot.slot_date]
    out: list[date] = []
    day = shift_start.date()
    last = shift_end.date()
    while day <= last:
        out.append(day)
        day += timedelta(days=1)
    return out


def _matches_avoid_time_window_band(
    *,
    db: Session,
    slot: RosterSlot,
    band: AvoidTimeWindowBand,
    band_index: int,
) -> dict[str, object] | None:
    interval = _resolve_slot_interval(db, slot)
    if interval is None:
        return None
    shift_start, shift_end = interval
    slot_tz = shift_start.tzinfo
    allowed_weekdays = {_WEEKDAY_TO_INDEX[code] for code in band.weekdays}
    for day in _days_for_anchor(slot=slot, shift_start=shift_start, shift_end=shift_end, anchor=band.anchor):
        if day.weekday() not in allowed_weekdays:
            continue
        window_start, window_end = _window_interval_for_day(
            day, band.window_start, band.window_end, tz=slot_tz
        )
        if _intervals_overlap(shift_start, shift_end, window_start, window_end):
            return {
                "weekday": _weekday_code(day),
                "window_start": band.window_start.strftime("%H:%M"),
                "window_end": band.window_end.strftime("%H:%M"),
                "slot_starts_at": shift_start.isoformat(),
                "slot_ends_at": shift_end.isoformat(),
                "anchor": band.anchor,
                "window_band_index": band_index,
            }
    return None


def _matches_avoid_time_window(
    *,
    db: Session,
    slot: RosterSlot,
    rule: AvoidTimeWindowMemberPatternRule,
) -> dict[str, object] | None:
    for index, band in enumerate(rule.windows):
        hit = _matches_avoid_time_window_band(db=db, slot=slot, band=band, band_index=index)
        if hit is not None:
            return hit
    return None


def _matches_week_parity(slot: RosterSlot, rule: AllowedCalendarWeekParityMemberPatternRule) -> dict[str, object] | None:
    iso_year, iso_week, _ = slot.slot_date.isocalendar()
    actual_parity = "even" if iso_week % 2 == 0 else "odd"
    if actual_parity == rule.parity:
        return None
    return {
        "iso_year": iso_year,
        "iso_week": iso_week,
        "actual_parity": actual_parity,
        "required_parity": rule.parity,
    }


def _resolved_patterns(rows: list[TeamMemberPlanningPattern]) -> list[ResolvedMemberPattern]:
    out: list[ResolvedMemberPattern] = []
    for row in rows:
        if not row.is_active:
            continue
        rule = _parse_rule(row.rule)
        out.append(
            ResolvedMemberPattern(
                pattern_id=row.id,
                label=row.label,
                severity=row.severity,
                rule=rule,
            )
        )
    return out


def evaluate_member_planning_patterns(
    *,
    db: Session,
    slot: RosterSlot,
    team_member_id: int,
    patterns: list[TeamMemberPlanningPattern],
    assignment_id: int | None = None,
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    for resolved in _resolved_patterns(patterns):
        if resolved.rule.type == "recurring_weekday_status":
            continue
        details: dict[str, object] = {
            "pattern_id": resolved.pattern_id,
            "pattern_label": resolved.label,
            "pattern_type": resolved.rule.type,
            "constraint_severity": resolved.severity,
            "roster_slot_id": slot.id,
            "shift_template_id": slot.shift_template_id,
            "shift_variant_id": slot.shift_variant_id,
        }
        if assignment_id is not None:
            details["roster_slot_assignment_id"] = assignment_id
        match: dict[str, object] | None
        if resolved.rule.type == "avoid_time_window":
            match = _matches_avoid_time_window(db=db, slot=slot, rule=resolved.rule)
            if match is None:
                continue
            details.update(match)
            details["constraint_severity"] = "info"
            warnings.append(
                ValidationWarning(
                    code="MEMBER_PATTERN_AVOID_TIME_WINDOW",
                    severity="info",
                    message="Member planning pattern: shift overlaps a restricted time window.",
                    team_member_id=team_member_id,
                    date=slot.slot_date,
                    details=details,
                )
            )
            continue
        if resolved.rule.type == "allowed_calendar_week_parity":
            match = _matches_week_parity(slot, resolved.rule)
            if match is None:
                continue
            details.update(match)
            warnings.append(
                ValidationWarning(
                    code="MEMBER_PATTERN_WEEK_PARITY",
                    severity=resolved.severity,
                    message="Member planning pattern: assignment is outside the allowed calendar week parity.",
                    team_member_id=team_member_id,
                    date=slot.slot_date,
                    details=details,
                )
            )
    return warnings


def list_patterns_for_members(
    db: Session, *, organization_id: int, team_member_ids: set[int]
) -> dict[int, list[TeamMemberPlanningPattern]]:
    if not team_member_ids:
        return {}
    rows = list(
        db.scalars(
            select(TeamMemberPlanningPattern).where(
                TeamMemberPlanningPattern.organization_id == organization_id,
                TeamMemberPlanningPattern.team_member_id.in_(team_member_ids),
            )
        )
    )
    out: dict[int, list[TeamMemberPlanningPattern]] = {member_id: [] for member_id in team_member_ids}
    for row in rows:
        out.setdefault(row.team_member_id, []).append(row)
    for member_id in out:
        out[member_id].sort(key=lambda item: (item.display_order, item.id))
    return out
