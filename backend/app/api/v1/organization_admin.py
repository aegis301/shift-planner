from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models import Organization, User
from app.schemas import (
    ApproveJoinCreateDoctorInput,
    ApproveJoinLinkDoctorBody,
    JoinRequestRead,
    OrganizationReadForAdmin,
    OrganizationUpdateInput,
    OrganizationUserRead,
)
from app.services.join_requests import (
    approve_join_request_create_doctor,
    approve_join_request_link_doctor,
    cancel_join_request_by_requester,
    get_join_request_in_org,
    join_request_to_read,
    list_join_requests_for_org,
    reject_join_request,
)
from app.services.organizations import update_organization_settings
from app.services.users import list_organization_users

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("/users", response_model=list[OrganizationUserRead])
def get_organization_users(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[OrganizationUserRead]:
    return list_organization_users(db, organization_id=user.organization_id)


@router.get("", response_model=OrganizationReadForAdmin)
def get_organization_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> Organization:
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.patch("", response_model=OrganizationReadForAdmin)
def patch_organization_settings(
    payload: OrganizationUpdateInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> Organization:
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    try:
        return update_organization_settings(
            db,
            org,
            name=payload.name,
            organization_slug=payload.organization_slug,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/join-requests", response_model=list[JoinRequestRead])
def get_join_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[JoinRequestRead]:
    rows = list_join_requests_for_org(db, organization_id=user.organization_id, status=status_filter)
    return [join_request_to_read(r) for r in rows]


@router.post("/join-requests/{request_id}/approve-create-doctor", response_model=JoinRequestRead)
def post_approve_join_create_doctor(
    request_id: int,
    payload: ApproveJoinCreateDoctorInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> JoinRequestRead:
    row = get_join_request_in_org(db, request_id=request_id, organization_id=user.organization_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    try:
        updated = approve_join_request_create_doctor(db, row=row, admin_user=user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return join_request_to_read(updated)


@router.post("/join-requests/{request_id}/approve-link-doctor", response_model=JoinRequestRead)
def post_approve_join_link_doctor(
    request_id: int,
    payload: ApproveJoinLinkDoctorBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> JoinRequestRead:
    row = get_join_request_in_org(db, request_id=request_id, organization_id=user.organization_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    try:
        updated = approve_join_request_link_doctor(
            db, row=row, admin_user=user, doctor_id=payload.doctor_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return join_request_to_read(updated)


@router.post("/join-requests/{request_id}/reject", response_model=JoinRequestRead)
def post_reject_join_request(
    request_id: int,
    reason: str | None = Query(default=None, max_length=2000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> JoinRequestRead:
    row = get_join_request_in_org(db, request_id=request_id, organization_id=user.organization_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    try:
        updated = reject_join_request(db, row=row, admin_user=user, reason=reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return join_request_to_read(updated)


@router.post("/join-requests/{request_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def post_cancel_own_join_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    ok = cancel_join_request_by_requester(db, request_id=request_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel this request")
