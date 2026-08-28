from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import User
from app.schemas import TeamMemberPropertyMatrixRead, TeamMemberPropertyMatrixSearch
from app.services.team_member_property_matrix import get_team_member_property_matrix

router = APIRouter(prefix="/team-member-property-matrix", tags=["team-member-property-matrix"])


@router.get("", response_model=TeamMemberPropertyMatrixRead)
def get_property_matrix(
    active_members_only: bool = True,
    active_definitions_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TeamMemberPropertyMatrixRead:
    return get_team_member_property_matrix(
        db,
        organization_id=user.organization_id,
        active_members_only=active_members_only,
        active_definitions_only=active_definitions_only,
    )


@router.post("/search", response_model=TeamMemberPropertyMatrixRead)
def search_property_matrix(
    payload: TeamMemberPropertyMatrixSearch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TeamMemberPropertyMatrixRead:
    try:
        return get_team_member_property_matrix(
            db,
            organization_id=user.organization_id,
            active_members_only=payload.active_members_only,
            active_definitions_only=payload.active_definitions_only,
            filters=payload.filters,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
