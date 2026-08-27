from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models import User
from app.schemas import TeamMemberPropertyValuesMatrixRead
from app.services.team_member_property_values import list_property_values_matrix

router = APIRouter(prefix="/team-member-property-values", tags=["team-member-property-values"])


@router.get("/matrix", response_model=TeamMemberPropertyValuesMatrixRead)
def get_team_member_property_values_matrix(
    active_definitions_only: bool = True,
    active_members_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> TeamMemberPropertyValuesMatrixRead:
    return list_property_values_matrix(
        db,
        organization_id=user.organization_id,
        active_definitions_only=active_definitions_only,
        active_members_only=active_members_only,
    )
