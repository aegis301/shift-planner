from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import User
from app.schemas import (
    TeamMemberPropertyDefinitionCreate,
    TeamMemberPropertyDefinitionRead,
    TeamMemberPropertyDefinitionUpdate,
)
from app.services.team_member_property_definitions import (
    create_team_member_property_definition,
    delete_team_member_property_definition,
    get_team_member_property_definition_or_none,
    list_team_member_property_definitions,
    update_team_member_property_definition,
)

router = APIRouter(prefix="/team-member-property-definitions", tags=["team-member-property-definitions"])


@router.get("", response_model=list[TeamMemberPropertyDefinitionRead])
def get_team_member_property_definitions(
    active_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[TeamMemberPropertyDefinitionRead]:
    rows = list_team_member_property_definitions(
        db, organization_id=user.organization_id, active_only=active_only
    )
    return [TeamMemberPropertyDefinitionRead.model_validate(row) for row in rows]


@router.post("", response_model=TeamMemberPropertyDefinitionRead, status_code=status.HTTP_201_CREATED)
def post_team_member_property_definition(
    payload: TeamMemberPropertyDefinitionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TeamMemberPropertyDefinitionRead:
    try:
        row = create_team_member_property_definition(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TeamMemberPropertyDefinitionRead.model_validate(row)


@router.patch("/{definition_id}", response_model=TeamMemberPropertyDefinitionRead)
def patch_team_member_property_definition(
    definition_id: int,
    payload: TeamMemberPropertyDefinitionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TeamMemberPropertyDefinitionRead:
    try:
        row = update_team_member_property_definition(
            db,
            definition_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Property definition not found")
    return TeamMemberPropertyDefinitionRead.model_validate(row)


@router.delete("/{definition_id}")
def delete_team_member_property_definition_endpoint(
    definition_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> dict[str, bool]:
    deleted = delete_team_member_property_definition(
        db,
        definition_id,
        organization_id=user.organization_id,
        actor=user.email,
        source="rest",
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Property definition not found")
    return {"deleted": True}
