from contextlib import contextmanager

from app.models import RosterSlot, ShiftGroupShiftTemplate
from app.models.base import Base
from app.services.roster_candidates import list_slot_candidates
from app.services.solver_fixture import seed_solver_fixture
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from mcp_app import server
from mcp_app.server import get_slot_candidates_tool


def test_get_slot_candidates_tool_returns_the_service_payload(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    try:
        result = seed_solver_fixture(db, profile="tight", rng_seed=1, year=2026, month=10, history_months=0)
        shift_group_id = result.shift_group_ids[0]
        slot = db.scalar(
            select(RosterSlot)
            .join(ShiftGroupShiftTemplate, ShiftGroupShiftTemplate.shift_template_id == RosterSlot.shift_template_id)
            .where(
                RosterSlot.planning_period_id == result.target_period_id,
                ShiftGroupShiftTemplate.shift_group_id == shift_group_id,
            )
            .order_by(RosterSlot.slot_date, RosterSlot.id)
        )
        assert slot is not None

        @contextmanager
        def same_session():
            yield db

        monkeypatch.setattr(server, "db_session", same_session)
        monkeypatch.setattr(server, "mcp_organization_id", lambda: result.organization_id)
        tool_payload = get_slot_candidates_tool(result.target_period_id, slot.id, shift_group_id)
        service_payload = list_slot_candidates(
            db,
            slot.id,
            organization_id=result.organization_id,
            shift_group_id=shift_group_id,
        ).model_dump(mode="json")
        assert tool_payload == service_payload
    finally:
        db.close()
        engine.dispose()
