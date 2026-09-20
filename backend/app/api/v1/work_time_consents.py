from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models import TeamMember, User
from app.schemas import (
    WorkTimeConsentCreate,
    WorkTimeConsentRead,
    WorkTimeConsentRevoke,
    WorkTimeConsentRevokeRead,
)
from app.services.authz import is_admin
from app.services.work_time_consents import (
    list_work_time_consents,
    record_work_time_consent,
    revoke_work_time_consent,
    work_time_consent_to_read,
)

router = APIRouter(prefix="/team-members", tags=["work-time-consents"])


def _assert_consent_read(db: Session, user: User, team_member_id: int) -> None:
    member = db.get(TeamMember, team_member_id)
    if member is None or member.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team member not found")
    if is_admin(user):
        return
    if member.user_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Consent records are admin or self read only")


@router.get("/{team_member_id}/work-time-consents", response_model=list[WorkTimeConsentRead])
def get_work_time_consents(
    team_member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkTimeConsentRead]:
    _assert_consent_read(db, user, team_member_id)
    rows = list_work_time_consents(db, team_member_id, organization_id=user.organization_id)
    return [work_time_consent_to_read(row) for row in rows]


@router.post("/{team_member_id}/work-time-consents", response_model=WorkTimeConsentRead)
def post_work_time_consent(
    team_member_id: int,
    payload: WorkTimeConsentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkTimeConsentRead:
    try:
        row = record_work_time_consent(
            db,
            team_member_id,
            payload,
            organization_id=user.organization_id,
            recorded_by_user_id=user.id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return work_time_consent_to_read(row)


@router.post(
    "/{team_member_id}/work-time-consents/{consent_id}/revoke",
    response_model=WorkTimeConsentRevokeRead,
)
def post_revoke_work_time_consent(
    team_member_id: int,
    consent_id: int,
    payload: WorkTimeConsentRevoke,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> WorkTimeConsentRevokeRead:
    try:
        row, findings = revoke_work_time_consent(
            db,
            consent_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row.team_member_id != team_member_id:
        raise HTTPException(status_code=404, detail="Consent record not found")
    return WorkTimeConsentRevokeRead(consent=work_time_consent_to_read(row), affected_plans=findings)
