import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Organization, PlanningDayStatusDefinition
from app.models.base import Base
from app.schemas import PlanningDayStatusDefinitionCreate
from app.services.planning_day_status_definitions import (
    assert_valid_planning_cell_status,
    cell_status_blocks_roster_assignment,
    create_planning_day_status_definition,
    ensure_default_planning_day_statuses,
    list_planning_day_status_definitions,
)


@pytest.fixture()
def status_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = session_local()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_default_day_statuses_seeded(status_db) -> None:
    ensure_default_planning_day_statuses(status_db, organization_id=1)
    rows = list_planning_day_status_definitions(status_db, organization_id=1)
    codes = {row.code for row in rows}
    assert codes == {"urlaub", "forschung", "lehre", "frei"}
    assert [row.label for row in rows] == sorted(row.label for row in rows)


def test_custom_status_validate_and_roster_block(status_db) -> None:
    ensure_default_planning_day_statuses(status_db, organization_id=1)
    create_planning_day_status_definition(
        status_db,
        PlanningDayStatusDefinitionCreate(
            code="fortbildung",
            label="Fortbildung",
            color_preset="emerald",
            blocks_roster_assignment=True,
        ),
        organization_id=1,
        actor="test",
        source="test",
    )
    assert_valid_planning_cell_status(status_db, organization_id=1, status="fortbildung")
    assert cell_status_blocks_roster_assignment(status_db, organization_id=1, status="fortbildung")


def test_non_blocking_status_allows_roster(status_db) -> None:
    ensure_default_planning_day_statuses(status_db, organization_id=1)
    row = create_planning_day_status_definition(
        status_db,
        PlanningDayStatusDefinitionCreate(
            code="homeoffice",
            label="Homeoffice",
            color_preset="sky",
            blocks_roster_assignment=False,
        ),
        organization_id=1,
        actor="test",
        source="test",
    )
    assert row.blocks_roster_assignment is False
    assert not cell_status_blocks_roster_assignment(status_db, organization_id=1, status="homeoffice")


def test_unknown_status_blocks_roster(status_db) -> None:
    ensure_default_planning_day_statuses(status_db, organization_id=1)
    assert cell_status_blocks_roster_assignment(status_db, organization_id=1, status="unknown_code")


def test_inactive_status_still_blocks_when_flag_set(status_db) -> None:
    ensure_default_planning_day_statuses(status_db, organization_id=1)
    row = status_db.scalars(
        select(PlanningDayStatusDefinition).where(
            PlanningDayStatusDefinition.organization_id == 1,
            PlanningDayStatusDefinition.code == "urlaub",
        )
    ).one()
    row.is_active = False
    status_db.commit()
    assert cell_status_blocks_roster_assignment(status_db, organization_id=1, status="urlaub")
