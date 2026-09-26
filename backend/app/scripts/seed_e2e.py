from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    Account,
    PlanningPeriod,
    ShiftGroup,
    TeamMember,
    TeamMemberShiftGroup,
    User,
    UserShiftGroup,
)
from app.schemas import TeamMemberUpdate
from app.services.authz import ROLE_ADMIN, ROLE_PLANNER, ROLE_TEAM_MEMBER
from app.services.organizations import get_organization_by_slug
from app.services.solver_fixture import (
    SolverFixtureError,
    SolverFixtureSafetyError,
    seed_solver_fixture,
)
from app.services.team_members import update_team_member
from app.services.users import get_account_by_email, get_user_in_organization

E2E_PROFILE = "comfortable"
E2E_RNG_SEED = 1
E2E_YEAR = 2026
E2E_MONTH = 10
E2E_HISTORY_MONTHS = 6
E2E_ORGANIZATION_SLUG = f"solver-fixture-{E2E_PROFILE}-{E2E_RNG_SEED}"
E2E_SHIFT_GROUP_CODE = "anaesthesie"
E2E_ADMIN_EMAIL = "e2e-admin@example.com"
E2E_PLANNER_EMAIL = "e2e-planner@example.com"
E2E_MEMBER_EMAIL = "e2e-member@example.com"
E2E_ACTOR = "seed_e2e"
E2E_SOURCE = "script"


class E2ESeedPasswordError(Exception):
    pass


@dataclass(frozen=True)
class E2ESeedResult:
    organization_id: int
    organization_slug: str
    target_period_id: int
    shift_group_id: int
    linked_team_member_id: int


def seed_e2e(db: Session, *, password: str) -> E2ESeedResult:
    if not password.strip():
        raise E2ESeedPasswordError("E2E_SEED_PASSWORD is required")
    organization = get_organization_by_slug(db, E2E_ORGANIZATION_SLUG)
    if organization is not None and organization.id == settings.default_organization_id:
        raise SolverFixtureSafetyError("Refusing to write into DEFAULT_ORGANIZATION_ID")
    if organization is None:
        seeded = seed_solver_fixture(
            db,
            profile=E2E_PROFILE,
            rng_seed=E2E_RNG_SEED,
            history_months=E2E_HISTORY_MONTHS,
            year=E2E_YEAR,
            month=E2E_MONTH,
        )
        organization = get_organization_by_slug(db, seeded.organization_slug)
        if organization is None:
            raise SolverFixtureError(f"Organization {seeded.organization_slug} was not created")
        if organization.id == settings.default_organization_id:
            raise SolverFixtureSafetyError("Refusing to write into DEFAULT_ORGANIZATION_ID")
    period, group, member = _fixture_targets(db, organization.id)
    _upsert_user(db, email=E2E_ADMIN_EMAIL, password=password, organization_id=organization.id, role=ROLE_ADMIN)
    planner = _upsert_user(
        db,
        email=E2E_PLANNER_EMAIL,
        password=password,
        organization_id=organization.id,
        role=ROLE_PLANNER,
    )
    member_user = _upsert_user(
        db,
        email=E2E_MEMBER_EMAIL,
        password=password,
        organization_id=organization.id,
        role=ROLE_TEAM_MEMBER,
    )
    group_ids = list(
        db.scalars(
            select(ShiftGroup.id)
            .where(ShiftGroup.organization_id == organization.id)
            .order_by(ShiftGroup.id)
        )
    )
    db.execute(delete(UserShiftGroup).where(UserShiftGroup.user_id == planner.id))
    for group_id in group_ids:
        db.add(UserShiftGroup(user_id=planner.id, shift_group_id=group_id))
    db.commit()
    linked = update_team_member(
        db,
        member.id,
        TeamMemberUpdate(user_id=member_user.id),
        organization_id=organization.id,
        actor=E2E_ACTOR,
        source=E2E_SOURCE,
    )
    if linked is None:
        raise SolverFixtureError(f"Team member {member.id} was not linked")
    return E2ESeedResult(
        organization_id=organization.id,
        organization_slug=organization.slug,
        target_period_id=period.id,
        shift_group_id=group.id,
        linked_team_member_id=linked.id,
    )


def _fixture_targets(db: Session, organization_id: int) -> tuple[PlanningPeriod, ShiftGroup, TeamMember]:
    period = db.scalar(
        select(PlanningPeriod).where(
            PlanningPeriod.organization_id == organization_id,
            PlanningPeriod.year == E2E_YEAR,
            PlanningPeriod.month == E2E_MONTH,
        )
    )
    if period is None:
        raise SolverFixtureError(f"Planning period {E2E_YEAR}-{E2E_MONTH:02d} not found")
    group = db.scalar(
        select(ShiftGroup).where(
            ShiftGroup.organization_id == organization_id,
            ShiftGroup.code == E2E_SHIFT_GROUP_CODE,
        )
    )
    if group is None:
        raise SolverFixtureError(f"Shift group {E2E_SHIFT_GROUP_CODE} not found")
    member = db.scalar(
        select(TeamMember)
        .join(TeamMemberShiftGroup, TeamMemberShiftGroup.team_member_id == TeamMember.id)
        .where(
            TeamMember.organization_id == organization_id,
            TeamMemberShiftGroup.shift_group_id == group.id,
            TeamMember.is_active.is_(True),
        )
        .order_by(TeamMember.id)
        .limit(1)
    )
    if member is None:
        raise SolverFixtureError(f"No active team member in {E2E_SHIFT_GROUP_CODE}")
    return period, group, member


def _upsert_user(
    db: Session,
    *,
    email: str,
    password: str,
    organization_id: int,
    role: str,
) -> User:
    normalized = email.strip().lower()
    existing = get_user_in_organization(db, normalized, organization_id)
    if existing is not None:
        existing.role = role
        existing.locale = "de"
        existing.is_active = True
        existing.account.hashed_password = hash_password(password)
        db.flush()
        return existing
    account = get_account_by_email(db, normalized)
    if account is None:
        account = Account(email=normalized, hashed_password=hash_password(password), locale="de")
        db.add(account)
        db.flush()
    else:
        account.hashed_password = hash_password(password)
    user = User(account_id=account.id, organization_id=organization_id, role=role, locale="de")
    db.add(user)
    db.flush()
    return user


def main() -> None:
    password = os.environ.get("E2E_SEED_PASSWORD", "").strip()
    if not password:
        print("E2E_SEED_PASSWORD is required", file=sys.stderr)
        raise SystemExit(2)
    try:
        with SessionLocal() as db:
            result = seed_e2e(db, password=password)
    except SolverFixtureSafetyError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
    except (SolverFixtureError, E2ESeedPasswordError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    print(
        f"Seeded {result.organization_slug} org {result.organization_id} "
        f"period {result.target_period_id} shift group {result.shift_group_id} "
        f"member {result.linked_team_member_id}"
    )


if __name__ == "__main__":
    main()
