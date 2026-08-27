import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Organization,
    TeamMember,
    TeamMemberPropertyDefinition,
    TeamMemberPropertyValue,
)
from app.models.base import Base
from app.schemas import (
    TeamMemberPropertyDefinitionCreate,
    TeamMemberPropertyDefinitionUpdate,
    TeamMemberPropertyValuesReplace,
    TeamMemberPropertyValueUpsertItem,
)
from app.services.team_member_property_definitions import (
    create_team_member_property_definition,
    delete_team_member_property_definition,
    update_team_member_property_definition,
)
from app.services.team_member_property_values import (
    list_property_values_for_member,
    list_property_values_matrix,
    replace_team_member_property_values,
    validate_property_value_for_definition,
)


@pytest.fixture()
def prop_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = TestingSessionLocal()
    db.add(Organization(id=1, name="Default", slug="default", plan_tier="team"))
    db.add(
        TeamMember(
            id=1,
            organization_id=1,
            first_name="A",
            last_name="B",
            email="a@example.com",
            employment_percentage=100,
        )
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_create_definition_select_requires_options(prop_db):
    with pytest.raises(ValueError):
        TeamMemberPropertyDefinitionCreate(name="Badge", type="select", options=[])


def test_validate_number_and_select(prop_db):
    defn = TeamMemberPropertyDefinition(
        organization_id=1,
        name="Years",
        type="number",
        options=[],
    )
    assert validate_property_value_for_definition(defn, 3) == 3
    defn.type = "select"
    defn.options = ["A", "B"]
    assert validate_property_value_for_definition(defn, "A") == "A"
    with pytest.raises(ValueError):
        validate_property_value_for_definition(defn, "C")


def test_replace_values_creates_and_clears(prop_db):
    db = prop_db
    defn = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(name="Training years", type="number"),
        organization_id=1,
        actor="test",
        source="test",
    )
    rows = replace_team_member_property_values(
        db,
        team_member_id=1,
        organization_id=1,
        payload=TeamMemberPropertyValuesReplace(
            values=[TeamMemberPropertyValueUpsertItem(property_definition_id=defn.id, value=2)]
        ),
        actor="test",
        source="test",
    )
    assert len(rows) == 1
    assert rows[0].value == 2
    stored = db.scalar(select(TeamMemberPropertyValue).where(TeamMemberPropertyValue.team_member_id == 1))
    assert stored is not None
    assert stored.value == 2
    replace_team_member_property_values(
        db,
        team_member_id=1,
        organization_id=1,
        payload=TeamMemberPropertyValuesReplace(
            values=[TeamMemberPropertyValueUpsertItem(property_definition_id=defn.id, value=None)]
        ),
        actor="test",
        source="test",
    )
    assert db.scalar(select(TeamMemberPropertyValue).where(TeamMemberPropertyValue.team_member_id == 1)) is None


def test_member_cannot_write_admin_only_definition(prop_db):
    db = prop_db
    admin_only = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(
            name="Admin note",
            type="text",
            editable_by_team_member=False,
        ),
        organization_id=1,
        actor="test",
        source="test",
    )
    with pytest.raises(PermissionError):
        replace_team_member_property_values(
            db,
            team_member_id=1,
            organization_id=1,
            payload=TeamMemberPropertyValuesReplace(
                values=[TeamMemberPropertyValueUpsertItem(property_definition_id=admin_only.id, value="secret")]
            ),
            actor="test",
            source="test",
            allow_definition_ids=set(),
        )


def test_block_option_removal_when_values_exist(prop_db):
    db = prop_db
    defn = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(name="Badge", type="select", options=["A", "B"]),
        organization_id=1,
        actor="test",
        source="test",
    )
    replace_team_member_property_values(
        db,
        team_member_id=1,
        organization_id=1,
        payload=TeamMemberPropertyValuesReplace(
            values=[TeamMemberPropertyValueUpsertItem(property_definition_id=defn.id, value="B")]
        ),
        actor="test",
        source="test",
    )
    with pytest.raises(ValueError):
        update_team_member_property_definition(
            db,
            defn.id,
            TeamMemberPropertyDefinitionUpdate(options=["A"]),
            organization_id=1,
            actor="test",
            source="test",
        )


def test_list_includes_definitions_without_values(prop_db):
    db = prop_db
    create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(name="Exam date", type="date"),
        organization_id=1,
        actor="test",
        source="test",
    )
    rows = list_property_values_for_member(db, team_member_id=1, organization_id=1)
    assert len(rows) == 1
    assert rows[0].value is None
    assert rows[0].type == "date"


def test_delete_definition_with_values_deactivates(prop_db):
    db = prop_db
    defn = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(name="Note", type="text"),
        organization_id=1,
        actor="test",
        source="test",
    )
    replace_team_member_property_values(
        db,
        team_member_id=1,
        organization_id=1,
        payload=TeamMemberPropertyValuesReplace(
            values=[TeamMemberPropertyValueUpsertItem(property_definition_id=defn.id, value="x")]
        ),
        actor="test",
        source="test",
    )
    assert delete_team_member_property_definition(
        db, defn.id, organization_id=1, actor="test", source="test"
    )
    db.refresh(defn)
    assert defn.is_active is False


def test_list_property_values_matrix(prop_db):
    db = prop_db
    db.add(
        TeamMember(
            id=2,
            organization_id=1,
            first_name="C",
            last_name="D",
            email="c@example.com",
            employment_percentage=100,
            is_active=False,
        )
    )
    db.commit()
    years = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(name="Years", type="number"),
        organization_id=1,
        actor="test",
        source="test",
    )
    badge = create_team_member_property_definition(
        db,
        TeamMemberPropertyDefinitionCreate(
            name="Badge", type="select", options=["A", "B"], is_active=False
        ),
        organization_id=1,
        actor="test",
        source="test",
    )
    replace_team_member_property_values(
        db,
        team_member_id=1,
        organization_id=1,
        payload=TeamMemberPropertyValuesReplace(
            values=[TeamMemberPropertyValueUpsertItem(property_definition_id=years.id, value=4)]
        ),
        actor="test",
        source="test",
    )
    matrix = list_property_values_matrix(db, organization_id=1, active_definitions_only=True)
    assert [row.id for row in matrix.definitions] == [years.id]
    assert badge.id not in {row.id for row in matrix.definitions}
    assert len(matrix.members) == 2
    active_row = next(row for row in matrix.members if row.id == 1)
    assert active_row.values[0].value == 4
    inactive_row = next(row for row in matrix.members if row.id == 2)
    assert inactive_row.is_active is False
    assert inactive_row.values[0].value is None
    active_only = list_property_values_matrix(
        db, organization_id=1, active_definitions_only=True, active_members_only=True
    )
    assert [row.id for row in active_only.members] == [1]
    all_defs = list_property_values_matrix(db, organization_id=1, active_definitions_only=False)
    assert {row.id for row in all_defs.definitions} == {years.id, badge.id}
