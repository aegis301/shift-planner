from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import RosterSlot, ShiftGroupShiftTemplate, TeamMemberShiftGroup
from app.models.base import Base
from app.schemas import RosterSlotAssignmentUpsert
from app.services.roster_candidates import list_slot_candidates
from app.services.roster_change_sets import (
    STATUS_APPLIED,
    STATUS_REFUSED,
    RosterChangeInput,
    apply_roster_change_set,
)
from app.services.roster_matrix import upsert_roster_slot_assignment
from app.services.rules import build_plan_state
from app.services.solver.model import SERVICE_MASK_COVER_TEMPLATE, eligibility_mask_for_slots
from app.services.solver_fixture import SolverFixtureResult, seed_solver_fixture

FUTURE_YEAR = 2099
PAST_YEAR = 2020
MONTH = 3
BOUNDARY = 15


@dataclass(frozen=True)
class SlotPair:
    member_id: int
    shift_group_id: int
    early_slot: RosterSlot
    late_slot: RosterSlot


@pytest.fixture()
def db() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db: Session, year: int) -> SolverFixtureResult:
    return seed_solver_fixture(
        db, profile="comfortable", rng_seed=1, year=year, month=MONTH, history_months=0
    )


def _group_slots(db: Session, result: SolverFixtureResult, shift_group_id: int) -> list[RosterSlot]:
    return list(
        db.scalars(
            select(RosterSlot)
            .join(
                ShiftGroupShiftTemplate,
                ShiftGroupShiftTemplate.shift_template_id == RosterSlot.shift_template_id,
            )
            .where(
                RosterSlot.planning_period_id == result.target_period_id,
                ShiftGroupShiftTemplate.shift_group_id == shift_group_id,
            )
            .order_by(RosterSlot.slot_date, RosterSlot.id)
        ).unique()
    )


def _ok_member_ids(db: Session, result: SolverFixtureResult, slot: RosterSlot, shift_group_id: int) -> set[int]:
    payload = list_slot_candidates(
        db, slot.id, organization_id=result.organization_id, shift_group_id=shift_group_id
    )
    return {row.team_member_id for row in payload.candidates if row.status == "ok"}


def _pick_pair(db: Session, result: SolverFixtureResult) -> SlotPair:
    shift_group_id = result.shift_group_ids[0]
    slots = _group_slots(db, result, shift_group_id)
    early = [slot for slot in slots if slot.slot_date.day < BOUNDARY - 2]
    late = [slot for slot in slots if slot.slot_date.day > BOUNDARY + 2]
    for early_slot in early[:6]:
        early_ok = _ok_member_ids(db, result, early_slot, shift_group_id)
        for late_slot in late[:6]:
            shared = early_ok & _ok_member_ids(db, result, late_slot, shift_group_id)
            if shared:
                return SlotPair(min(shared), shift_group_id, early_slot, late_slot)
    raise AssertionError("fixture has no member who is ok on both an early and a late slot")


def _set_stints(db: Session, member_id: int, *, start_date: date, end_date: date | None) -> None:
    stints = db.scalars(
        select(TeamMemberShiftGroup).where(TeamMemberShiftGroup.team_member_id == member_id)
    ).all()
    assert stints
    for stint in stints:
        stint.start_date = start_date
        stint.end_date = end_date
    db.commit()


def _candidate(db: Session, result: SolverFixtureResult, pair: SlotPair, slot: RosterSlot):
    payload = list_slot_candidates(
        db, slot.id, organization_id=result.organization_id, shift_group_id=pair.shift_group_id
    )
    return next(row for row in payload.candidates if row.team_member_id == pair.member_id)


def _single_cell_accepts(db: Session, result: SolverFixtureResult, pair: SlotPair, slot: RosterSlot) -> bool:
    try:
        upsert_roster_slot_assignment(
            db,
            RosterSlotAssignmentUpsert(roster_slot_id=slot.id, team_member_id=pair.member_id),
            organization_id=result.organization_id,
            actor="test",
            source="test",
            commit=False,
        )
    except ValueError as exc:
        assert "shift group that covers this template" in str(exc)
        return False
    finally:
        db.rollback()
    return True


def _change_set_status(db: Session, result: SolverFixtureResult, pair: SlotPair, slot: RosterSlot) -> tuple[str, str | None]:
    change_set = apply_roster_change_set(
        db,
        organization_id=result.organization_id,
        planning_period_id=result.target_period_id,
        shift_group_id=pair.shift_group_id,
        items=[RosterChangeInput(roster_slot_id=slot.id, team_member_id=pair.member_id)],
        mode="all_or_nothing",
        actor="test",
        source="test",
        created_by_user_id=None,
    )
    status = change_set.status
    refusal = change_set.items[0].refusal_code
    return status, refusal


def _solver_mask(db: Session, result: SolverFixtureResult, pair: SlotPair) -> tuple[dict[int, set[int]], dict[tuple[int, int], list[str]]]:
    slots = [pair.early_slot, pair.late_slot]
    state = build_plan_state(
        db,
        organization_id=result.organization_id,
        start_date=pair.early_slot.slot_date,
        end_date=pair.late_slot.slot_date,
    )
    return eligibility_mask_for_slots(db, state=state, target_slots=slots)


def _assert_covers(db: Session, result: SolverFixtureResult, pair: SlotPair, *, inside: RosterSlot, outside: RosterSlot) -> None:
    eligible, exclusions = _solver_mask(db, result, pair)
    assert pair.member_id in eligible[inside.id]
    assert pair.member_id not in eligible[outside.id]
    assert SERVICE_MASK_COVER_TEMPLATE in exclusions[(outside.id, pair.member_id)]

    inside_candidate = _candidate(db, result, pair, inside)
    assert inside_candidate.status == "ok"
    assert inside_candidate.refusal is None
    outside_candidate = _candidate(db, result, pair, outside)
    assert outside_candidate.status == "blocked"
    assert outside_candidate.refusal is not None
    assert outside_candidate.refusal.code == "not_in_covering_group"

    assert _single_cell_accepts(db, result, pair, inside)
    assert not _single_cell_accepts(db, result, pair, outside)

    assert _change_set_status(db, result, pair, outside) == (STATUS_REFUSED, "CANNOT_COVER_TEMPLATE")
    status, refusal = _change_set_status(db, result, pair, inside)
    assert status == STATUS_APPLIED
    assert refusal is None


def test_stint_starting_after_today_covers_slots_inside_the_stint_only(db: Session):
    result = _seed(db, FUTURE_YEAR)
    pair = _pick_pair(db, result)
    _set_stints(db, pair.member_id, start_date=date(FUTURE_YEAR, MONTH, BOUNDARY), end_date=None)
    assert date.today() < date(FUTURE_YEAR, MONTH, BOUNDARY)
    _assert_covers(db, result, pair, inside=pair.late_slot, outside=pair.early_slot)


def test_stint_ended_before_today_covers_an_older_month(db: Session):
    result = _seed(db, PAST_YEAR)
    pair = _pick_pair(db, result)
    _set_stints(
        db,
        pair.member_id,
        start_date=date(PAST_YEAR - 1, 1, 1),
        end_date=date(PAST_YEAR, MONTH, BOUNDARY),
    )
    assert date.today() > date(PAST_YEAR, MONTH, BOUNDARY)
    _assert_covers(db, result, pair, inside=pair.early_slot, outside=pair.late_slot)
