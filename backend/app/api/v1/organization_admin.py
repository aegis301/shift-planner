from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models import Organization, User
from app.schemas import (
    AdminResetUserPasswordInput,
    ApproveJoinCreateTeamMemberInput,
    ApproveJoinLinkTeamMemberBody,
    DeleteOrganizationInput,
    JoinRequestRead,
    OrganizationInviteCreate,
    OrganizationMemberPatternPolicy,
    OrganizationMemberPatternPolicyRead,
    OrganizationMemberPatternPolicyUpdate,
    OrganizationMembershipInviteRead,
    OrganizationReadForAdmin,
    OrganizationStaffDirectoryRow,
    OrganizationUpdateInput,
    OrganizationUserRead,
    OrganizationUserRolePatch,
)
from app.services.join_requests import (
    approve_join_request_create_team_member,
    approve_join_request_link_team_member,
    cancel_join_request_by_requester,
    get_join_request_in_org,
    join_request_to_read,
    list_join_requests_for_org,
    reject_join_request,
)
from app.services.member_planning_patterns import (
    read_organization_member_pattern_policy,
    update_organization_member_pattern_policy,
)
from app.services.organization_directory import list_organization_staff_directory
from app.services.organization_invites import (
    create_membership_invite,
    invite_to_read,
    list_membership_invites_for_org,
    revoke_membership_invite,
)
from app.services.organization_lifecycle import delete_organization
from app.services.organizations import update_organization_settings
from app.services.users import (
    admin_delete_organization_user,
    admin_reset_account_password,
    admin_set_organization_user_role,
    list_organization_users,
)

router = APIRouter(prefix="/organization", tags=["organization"])


@router.get("/users", response_model=list[OrganizationUserRead])
def get_organization_users(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[OrganizationUserRead]:
    return list_organization_users(db, organization_id=user.organization_id)


@router.get("/staff-directory", response_model=list[OrganizationStaffDirectoryRow])
def get_organization_staff_directory(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[OrganizationStaffDirectoryRow]:
    return list_organization_staff_directory(db, organization_id=user.organization_id)


@router.delete("/users/{target_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_user(
    target_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> None:
    try:
        admin_delete_organization_user(db, actor=user, target_user_id=target_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/users/{target_user_id}", response_model=OrganizationUserRead)
def patch_organization_user_role(
    target_user_id: int,
    payload: OrganizationUserRolePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationUserRead:
    try:
        return admin_set_organization_user_role(db, actor=user, target_user_id=target_user_id, role=payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/users/{target_user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def post_organization_user_reset_password(
    target_user_id: int,
    payload: AdminResetUserPasswordInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> None:
    try:
        admin_reset_account_password(
            db, actor=user, target_user_id=target_user_id, new_password=payload.password
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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


@router.get("/member-pattern-policy", response_model=OrganizationMemberPatternPolicyRead)
def get_member_pattern_policy(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationMemberPatternPolicyRead:
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return read_organization_member_pattern_policy(org)


@router.patch("/member-pattern-policy", response_model=OrganizationMemberPatternPolicyRead)
def patch_member_pattern_policy(
    payload: OrganizationMemberPatternPolicyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationMemberPatternPolicyRead:
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return update_organization_member_pattern_policy(
        db,
        org,
        policy=OrganizationMemberPatternPolicy.model_validate(payload.model_dump()),
        actor=user.email,
        source="rest",
    )


@router.get("/join-requests", response_model=list[JoinRequestRead])
def get_join_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[JoinRequestRead]:
    rows = list_join_requests_for_org(db, organization_id=user.organization_id, status=status_filter)
    return [join_request_to_read(r) for r in rows]


@router.post("/join-requests/{request_id}/approve-create-team-member", response_model=JoinRequestRead)
def post_approve_join_create_team_member(
    request_id: int,
    payload: ApproveJoinCreateTeamMemberInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> JoinRequestRead:
    row = get_join_request_in_org(db, request_id=request_id, organization_id=user.organization_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    try:
        updated = approve_join_request_create_team_member(db, row=row, admin_user=user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return join_request_to_read(updated)


@router.post("/join-requests/{request_id}/approve-link-team-member", response_model=JoinRequestRead)
def post_approve_join_link_team_member(
    request_id: int,
    payload: ApproveJoinLinkTeamMemberBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> JoinRequestRead:
    row = get_join_request_in_org(db, request_id=request_id, organization_id=user.organization_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join request not found")
    try:
        updated = approve_join_request_link_team_member(
            db, row=row, admin_user=user, team_member_id=payload.team_member_id
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


@router.get("/invites", response_model=list[OrganizationMembershipInviteRead])
def get_organization_invites(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> list[OrganizationMembershipInviteRead]:
    rows = list_membership_invites_for_org(db, organization_id=user.organization_id)
    return [invite_to_read(db, r) for r in rows]


@router.post("/invites", response_model=OrganizationMembershipInviteRead)
def post_organization_invite(
    payload: OrganizationInviteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> OrganizationMembershipInviteRead:
    try:
        row = create_membership_invite(db, actor=user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return invite_to_read(db, row)


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> None:
    try:
        revoke_membership_invite(db, actor=user, invite_id=invite_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_organization_endpoint(
    payload: DeleteOrganizationInput = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> None:
    try:
        delete_organization(db, actor=user, confirm_organization_name=payload.confirm_organization_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
