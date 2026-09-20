from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Organization,
    PlanningPeriod,
    PlanningPeriodShiftGroupMember,
    PlanningPlanVersion,
    ShiftGroup,
    TeamMember,
    TimeEntry,
    WorkTimeConsent,
    WorkTimeRuleSet,
)
from app.models.base import Base
from app.schemas import WorkTimeConsentCreate, WorkTimeConsentRevoke, WorkTimeRuleOptOutWeeklyCap
from app.services.rules import build_plan_state
from app.services.rules.statutory import OptOutWeeklyCapRule
from app.services.work_time_consents import (
    applicable_weekly_cap,
    derive_effective_until,
    record_work_time_consent,
    revoke_work_time_consent,
)

pytest_plugins = ("app.tests.test_api",)


def login(client: TestClient, email: str = "admin@example.com", password: str = "secret") -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "organization_slug": "default"},
    ).status_code == 200


def login_team_member(client: TestClient) -> None:
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "doc@example.com", "password": "docsecret", "organization_slug": "default"},
    ).status_code == 200


@pytest.fixture()
def consent_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = testing_session()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _member(db: Session) -> TeamMember:
    member = TeamMember(
        organization_id=1,
        first_name="Opt",
        last_name="Out",
        email="opt-out@example.com",
        is_active=True,
    )
    db.add(member)
    db.flush()
    return member


def _opt_out_rule() -> WorkTimeRuleOptOutWeeklyCap:
    return WorkTimeRuleOptOutWeeklyCap(
        hours_by_tier={"standard": Decimal("48"), "stufe_i": Decimal("58")},
        reference_period_months=3,
    )


def test_applicable_weekly_cap_without_consent_uses_base():
    rule = _opt_out_rule()
    assert applicable_weekly_cap(1, date(2026, 3, 15), rule, []) == Decimal("48")


def test_applicable_weekly_cap_spans_revocation_boundary_in_one_run():
    rule = _opt_out_rule()
    revoked_at = date(2026, 3, 11)
    notice = 1
    until = derive_effective_until(revoked_at=revoked_at, notice_period_months=notice)
    assert until == date(2026, 4, 11)
    consent = WorkTimeConsent(
        id=1,
        organization_id=1,
        team_member_id=7,
        consent_type="opt_out",
        tier="stufe_i",
        valid_from=date(2026, 1, 1),
        revoked_at=revoked_at,
        notice_period_months=notice,
        effective_until=until,
    )
    assert applicable_weekly_cap(7, date(2026, 4, 11), rule, [consent]) == Decimal("58")
    assert applicable_weekly_cap(7, date(2026, 4, 12), rule, [consent]) == Decimal("48")


def test_opt_out_evaluation_applies_both_caps_across_revocation(consent_db):
    db = consent_db
    member = _member(db)
    revoked_at = date(2026, 3, 11)
    until = derive_effective_until(revoked_at=revoked_at, notice_period_months=1)
    db.add(
        WorkTimeConsent(
            organization_id=1,
            team_member_id=member.id,
            consent_type="opt_out",
            tier="stufe_i",
            valid_from=date(2026, 1, 1),
            revoked_at=revoked_at,
            notice_period_months=1,
            effective_until=until,
        )
    )
    db.add(
        WorkTimeRuleSet(
            organization_id=1,
            name="opt-out",
            version=1,
            is_active=True,
            rules=[
                {
                    "type": "opt_out_weekly_cap",
                    "severity": "warning",
                    "hours_by_tier": {"standard": "48", "stufe_i": "58"},
                    "reference_period_months": 3,
                }
            ],
        )
    )
    cursor = date(2025, 12, 31)
    last = date(2026, 5, 31)
    while cursor <= last:
        db.add(
            TimeEntry(
                organization_id=1,
                team_member_id=member.id,
                entry_date=cursor,
                kind="work",
                source="manual",
                duration_minutes=429,
                statutory_minutes=429,
            )
        )
        cursor += timedelta(days=1)
    db.commit()
    warnings = OptOutWeeklyCapRule(_opt_out_rule()).evaluate(
        build_plan_state(db, organization_id=1, start_date=date(2026, 3, 1), end_date=date(2026, 5, 31))
    )
    opt_out_days = [row.date for row in warnings if row.details["cap_minutes"] == 58 * 60]
    base_days = [row.date for row in warnings if row.details["cap_minutes"] == 48 * 60]
    assert opt_out_days == []
    assert base_days
    assert min(base_days) == date(2026, 4, 12)
    assert all(day >= date(2026, 4, 12) for day in base_days)


def test_consent_records_are_immutable_corrections_create_new_row(consent_db):
    db = consent_db
    member = _member(db)
    first = record_work_time_consent(
        db,
        member.id,
        WorkTimeConsentCreate(tier="stufe_i", valid_from=date(2026, 1, 1)),
        organization_id=1,
        recorded_by_user_id=None,
        actor="test",
        source="test",
    )
    second = record_work_time_consent(
        db,
        member.id,
        WorkTimeConsentCreate(tier="stufe_ii", valid_from=date(2026, 2, 1), signed_document_reference="corr-1"),
        organization_id=1,
        recorded_by_user_id=None,
        actor="test",
        source="test",
    )
    assert first.id != second.id
    db.refresh(first)
    assert first.tier == "stufe_i"
    assert first.signed_document_reference is None


def test_second_revoke_rejected_after_first(consent_db):
    db = consent_db
    member = _member(db)
    row = record_work_time_consent(
        db,
        member.id,
        WorkTimeConsentCreate(tier="stufe_i", valid_from=date(2026, 1, 1)),
        organization_id=1,
        recorded_by_user_id=None,
        actor="test",
        source="test",
    )
    revoke_work_time_consent(
        db,
        row.id,
        WorkTimeConsentRevoke(revoked_at=date(2026, 3, 11), notice_period_months=1),
        organization_id=1,
        actor="test",
        source="test",
    )
    with pytest.raises(ValueError, match="immutable"):
        revoke_work_time_consent(
            db,
            row.id,
            WorkTimeConsentRevoke(revoked_at=date(2026, 4, 1)),
            organization_id=1,
            actor="test",
            source="test",
        )


def test_revocation_lists_affected_future_published_plans(consent_db):
    db = consent_db
    member = _member(db)
    group = ShiftGroup(organization_id=1, code="sg", name="SG")
    db.add(group)
    db.flush()
    period = PlanningPeriod(organization_id=1, year=2027, month=1, status="published")
    db.add(period)
    db.flush()
    db.add(
        PlanningPeriodShiftGroupMember(
            planning_period_id=period.id, shift_group_id=group.id, team_member_id=member.id
        )
    )
    version = PlanningPlanVersion(
        organization_id=1,
        planning_period_id=period.id,
        shift_group_id=group.id,
        major_version=1,
        minor_version=0,
        lifecycle_phase="published",
        trigger="publish",
    )
    db.add(version)
    db.add(
        WorkTimeRuleSet(
            organization_id=1,
            name="opt-out",
            version=1,
            is_active=True,
            rules=[
                {
                    "type": "opt_out_weekly_cap",
                    "severity": "warning",
                    "hours_by_tier": {"standard": "48", "stufe_i": "58"},
                    "reference_period_months": 1,
                }
            ],
        )
    )
    db.add(
        TimeEntry(
            organization_id=1,
            team_member_id=member.id,
            entry_date=date(2027, 1, 20),
            kind="work",
            source="manual",
            duration_minutes=13714,
            statutory_minutes=13714,
        )
    )
    db.commit()
    consent = record_work_time_consent(
        db,
        member.id,
        WorkTimeConsentCreate(tier="stufe_i", valid_from=date(2026, 1, 1)),
        organization_id=1,
        recorded_by_user_id=None,
        actor="test",
        source="test",
    )
    _row, findings = revoke_work_time_consent(
        db,
        consent.id,
        WorkTimeConsentRevoke(revoked_at=date(2026, 1, 1), notice_period_months=1),
        organization_id=1,
        actor="test",
        source="test",
    )
    assert findings
    assert findings[0].planning_period_id == period.id
    assert findings[0].planning_plan_version_id == version.id
    assert "WORKTIME_WEEKLY_AVERAGE_OPT_OUT" in findings[0].warning_codes
    db.refresh(version)
    assert version.lifecycle_phase == "published"
    assert version.note is None


def test_member_cannot_record_own_consent(team_member_client: TestClient):
    login_team_member(team_member_client)
    me = team_member_client.get("/api/v1/auth/me").json()
    member_id = me["team_member_id"]
    denied = team_member_client.post(
        f"/api/v1/team-members/{member_id}/work-time-consents",
        json={"tier": "stufe_i", "valid_from": "2026-01-01"},
    )
    assert denied.status_code == 403
    listed = team_member_client.get(f"/api/v1/team-members/{member_id}/work-time-consents")
    assert listed.status_code == 200
    login(team_member_client)
    created = team_member_client.post(
        f"/api/v1/team-members/{member_id}/work-time-consents",
        json={"tier": "stufe_i", "valid_from": "2026-01-01", "signed_document_reference": "doc-1"},
    )
    assert created.status_code == 200, created.text
    consent_id = created.json()["id"]
    patched = team_member_client.patch(
        f"/api/v1/team-members/{member_id}/work-time-consents/{consent_id}",
        json={"tier": "stufe_ii"},
    )
    assert patched.status_code in {404, 405}
    login_team_member(team_member_client)
    assert team_member_client.get(f"/api/v1/team-members/{member_id}/work-time-consents").json()[0]["tier"] == "stufe_i"
