from calendar import monthrange
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlanningPeriodShiftGroupMember, TeamMember
from app.schemas import (
    ComplianceMemberReport,
    ComplianceReportRead,
    ComplianceRestViolation,
    ComplianceRuleSetRef,
    ValidationWarning,
)
from app.services.planning_period_rosters import team_member_ids_for_period_shift_group
from app.services.rules import build_plan_state, evaluate_plan_state
from app.services.rules.statutory import member_worktime_metrics, statutory_rules_for_org
from app.services.shift_groups import require_shift_group
from app.services.team_members import team_member_planning_display_name
from app.services.tenancy import require_planning_period_in_org
from app.services.validation import filter_warnings_for_shift_group
from app.services.work_time_rule_sets import get_active_work_time_rule_set

_REST_CODES = {
    "WORKTIME_MIN_REST",
    "WORKTIME_REST_COMPENSATION_PENDING",
    "WORKTIME_REST_AFTER_LONG_DUTY",
}


def _sort_findings(warnings: list[ValidationWarning]) -> list[ValidationWarning]:
    return sorted(
        warnings,
        key=lambda row: (
            row.code,
            row.team_member_id or 0,
            row.date.isoformat() if row.date is not None else "",
            row.message,
            str(sorted(row.details.items())),
        ),
    )


def _member_ids_for_report(
    db: Session, *, planning_period_id: int, shift_group_id: int | None
) -> set[int]:
    if shift_group_id is not None:
        return team_member_ids_for_period_shift_group(
            db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
        )
    rows = db.scalars(
        select(PlanningPeriodShiftGroupMember.team_member_id).where(
            PlanningPeriodShiftGroupMember.planning_period_id == planning_period_id
        )
    ).all()
    return set(rows)


def _rest_violations(findings: list[ValidationWarning], member_id: int) -> list[ComplianceRestViolation]:
    rows: list[ComplianceRestViolation] = []
    for warning in findings:
        if warning.team_member_id != member_id or warning.code not in _REST_CODES:
            continue
        rest_minutes = warning.details.get("rest_minutes")
        rows.append(
            ComplianceRestViolation(
                code=warning.code,
                severity=warning.severity,
                date=warning.date,
                message=warning.message,
                rest_minutes=rest_minutes if isinstance(rest_minutes, int) else None,
                compensation_pending=warning.code == "WORKTIME_REST_COMPENSATION_PENDING",
            )
        )
    return rows


def build_compliance_report(
    db: Session,
    planning_period_id: int,
    *,
    organization_id: int,
    shift_group_id: int | None = None,
    generated_at: datetime | None = None,
) -> ComplianceReportRead:
    period = require_planning_period_in_org(db, planning_period_id, organization_id)
    if shift_group_id is not None:
        require_shift_group(db, shift_group_id, organization_id)
    start_date = datetime(period.year, period.month, 1).date()
    end_date = start_date.replace(day=monthrange(period.year, period.month)[1])
    state = build_plan_state(
        db,
        organization_id=organization_id,
        start_date=start_date,
        end_date=end_date,
    )
    findings = _sort_findings(
        filter_warnings_for_shift_group(
            db,
            evaluate_plan_state(state, db=db),
            planning_period_id=planning_period_id,
            organization_id=organization_id,
            shift_group_id=shift_group_id,
        )
    )
    member_ids = _member_ids_for_report(
        db, planning_period_id=planning_period_id, shift_group_id=shift_group_id
    )
    if not member_ids:
        member_ids = set(state.members_by_id)
    members = list(
        db.scalars(
            select(TeamMember)
            .where(TeamMember.organization_id == organization_id, TeamMember.id.in_(member_ids))
            .order_by(TeamMember.last_name, TeamMember.first_name, TeamMember.id)
        )
    )
    statutory_rules = statutory_rules_for_org(db, organization_id)
    member_rows: list[ComplianceMemberReport] = []
    for member in members:
        metrics = member_worktime_metrics(state, member.id, statutory_rules)
        member_findings = [row for row in findings if row.team_member_id == member.id]
        member_rows.append(
            ComplianceMemberReport(
                team_member_id=member.id,
                display_name=team_member_planning_display_name(member),
                rest_violations=_rest_violations(findings, member.id),
                findings=member_findings,
                **metrics,
            )
        )
    rule_set = get_active_work_time_rule_set(db, organization_id=organization_id)
    stamp = generated_at if generated_at is not None else datetime.now(UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return ComplianceReportRead(
        planning_period_id=period.id,
        year=period.year,
        month=period.month,
        shift_group_id=shift_group_id,
        generated_at=stamp,
        rule_set=(
            ComplianceRuleSetRef(id=rule_set.id, name=rule_set.name, version=rule_set.version)
            if rule_set is not None
            else None
        ),
        members=member_rows,
        findings=findings,
    )
