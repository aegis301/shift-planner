import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Organization, TeamMember, TeamMemberPropertyDefinition
from app.models.base import Base
from app.schemas import TeamMemberPropertyDefinitionCreate, ShiftConstraint
from app.services.shift_templates import ShiftConstraintInvalidError, validate_shift_constraint_payloads
from app.services.team_member_property_definitions import create_team_member_property_definition
from app.services.team_member_property_requirements import (
    TeamMemberPropertyRequirementError,
    collect_property_requirement_violations,
    evaluate_property_requirement_expr,
    validate_property_requirement_expr,
)


@pytest.fixture()
def req_db():
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


def test_validate_rejects_unknown_property(req_db):
    db = req_db
    expr = ShiftConstraint.model_validate(
        {
            "type": "team_member_property_requirement",
            "severity": "warning",
            "property_requirement": {
                "kind": "atom",
                "property_definition_id": 99,
                "op": "gte",
                "value": 1,
            },
        }
    ).property_requirement
    assert expr is not None
    with pytest.raises(TeamMemberPropertyRequirementError, match="not found"):
        validate_property_requirement_expr(db, expr, organization_id=1)


def test_validate_rejects_invalid_op_for_type(req_db):
    db = req_db
    row = create_team_member_property_definition(
        db,
        organization_id=1,
        payload=TeamMemberPropertyDefinitionCreate(name="N", type="number"),
        actor="t",
        source="t",
    )
    expr = ShiftConstraint.model_validate(
        {
            "type": "team_member_property_requirement",
            "property_requirement": {
                "kind": "atom",
                "property_definition_id": row.id,
                "op": "contains",
                "value": "x",
            },
        }
    ).property_requirement
    assert expr is not None
    with pytest.raises(TeamMemberPropertyRequirementError, match="Invalid operator"):
        validate_property_requirement_expr(db, expr, organization_id=1)


def test_validate_shift_constraint_wraps_error(req_db):
    db = req_db
    bad = [
        {
            "type": "team_member_property_requirement",
            "property_requirement": {
                "kind": "atom",
                "property_definition_id": 123,
                "op": "gte",
                "value": 1,
            },
        }
    ]
    with pytest.raises(ShiftConstraintInvalidError, match="not found"):
        validate_shift_constraint_payloads(db, bad, organization_id=1)


def test_evaluate_number_gte_and_any(req_db):
    db = req_db
    row = create_team_member_property_definition(
        db,
        organization_id=1,
        payload=TeamMemberPropertyDefinitionCreate(name="Years", type="number"),
        actor="t",
        source="t",
    )
    defs = {row.id: row}
    expr_all = ShiftConstraint.model_validate(
        {
            "type": "team_member_property_requirement",
            "property_requirement": {
                "kind": "all",
                "items": [
                    {"kind": "atom", "property_definition_id": row.id, "op": "gte", "value": 3},
                ],
            },
        }
    ).property_requirement
    assert expr_all is not None
    assert evaluate_property_requirement_expr(expr_all, {row.id: 2}, defs) is False
    assert evaluate_property_requirement_expr(expr_all, {row.id: 4}, defs) is True
    assert evaluate_property_requirement_expr(expr_all, {}, defs) is False

    expr_any = ShiftConstraint.model_validate(
        {
            "type": "team_member_property_requirement",
            "property_requirement": {
                "kind": "any",
                "items": [
                    {"kind": "atom", "property_definition_id": row.id, "op": "eq", "value": 1},
                    {"kind": "atom", "property_definition_id": row.id, "op": "eq", "value": 2},
                ],
            },
        }
    ).property_requirement
    assert expr_any is not None
    assert evaluate_property_requirement_expr(expr_any, {row.id: 2}, defs) is True
    assert evaluate_property_requirement_expr(expr_any, {row.id: 5}, defs) is False


def test_evaluate_select_one_of(req_db):
    db = req_db
    row = TeamMemberPropertyDefinition(
        organization_id=1,
        name="Role",
        type="select",
        options=["a", "b"],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    defs = {row.id: row}
    expr = ShiftConstraint.model_validate(
        {
            "type": "team_member_property_requirement",
            "property_requirement": {
                "kind": "atom",
                "property_definition_id": row.id,
                "op": "one_of",
                "value": ["a", "b"],
            },
        }
    ).property_requirement
    assert expr is not None
    assert evaluate_property_requirement_expr(expr, {row.id: "a"}, defs) is True
    assert evaluate_property_requirement_expr(expr, {row.id: "c"}, defs) is False


def test_collect_violations_reports_property_and_values(req_db):
    db = req_db
    row = create_team_member_property_definition(
        db,
        organization_id=1,
        payload=TeamMemberPropertyDefinitionCreate(name="Training year", type="number"),
        actor="t",
        source="t",
    )
    defs = {row.id: row}
    expr = ShiftConstraint.model_validate(
        {
            "type": "team_member_property_requirement",
            "property_requirement": {
                "kind": "atom",
                "property_definition_id": row.id,
                "op": "gte",
                "value": 3,
            },
        }
    ).property_requirement
    assert expr is not None
    violations = collect_property_requirement_violations(expr, {row.id: 1}, defs)
    assert len(violations) == 1
    assert violations[0]["property_name"] == "Training year"
    assert violations[0]["op"] == "gte"
    assert violations[0]["required_value"] == 3
    assert violations[0]["actual_value"] == 1
    assert violations[0]["missing"] is False

    missing = collect_property_requirement_violations(expr, {}, defs)
    assert len(missing) == 1
    assert missing[0]["missing"] is True
    assert missing[0]["actual_value"] is None
