from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_account_session,
    get_current_session_holder,
    get_current_user,
)
from app.core.config import settings
from app.core.security import (
    SESSION_MAX_AGE_SECONDS,
    create_account_session_token,
    create_user_session_token,
)
from app.db.session import get_db
from app.models import Account, User
from app.schemas import (
    AccountSessionRead,
    ActiveOrganizationInput,
    AddOrganizationMembershipInput,
    AuthLoginResponse,
    AuthMeResponse,
    CreateOrganizationMembershipInput,
    DeleteAccountInput,
    JoinRequestRead,
    JoinRequestResubmitInput,
    LoginInput,
    OnboardingCreateOrganizationInput,
    OnboardingJoinOrganizationInput,
    OrganizationInviteAcceptInput,
    OrganizationMembershipInvitePendingRead,
    RegisterAccountInput,
    RegisterCreateOrganizationInput,
    RegisterJoinOrganizationInput,
    TeamMemberRead,
    TeamMemberSelfUpdate,
    UserRead,
)
from app.services.authz import get_linked_team_member
from app.services.registration import (
    create_additional_organization_membership,
    onboarding_create_organization,
    onboarding_join_organization,
    register_account_only,
    register_create_organization,
    register_join_organization,
    request_join_additional_organization,
)
from app.services.join_requests import (
    create_join_request_for_applicant,
    get_pending_join_request_for_user,
    join_request_to_read,
)
from app.services.organization_invites import (
    accept_membership_invite,
    decline_membership_invite,
    invite_pending_to_read,
    list_pending_invites_for_account,
)
from app.services.team_members import team_member_to_read
from app.services.users import (
    authenticate_login,
    build_account_session_read,
    build_user_read,
    delete_own_account,
    switch_membership_by_organization_slug,
    update_self_team_member_profile,
)


def _set_user_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        "shift_planner_session",
        create_user_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def _set_account_session_cookie(response: Response, account_id: int) -> None:
    response.set_cookie(
        "shift_planner_session",
        create_account_session_token(account_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        "shift_planner_session",
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=AuthLoginResponse)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> UserRead | AccountSessionRead:
    auth = authenticate_login(
        db,
        email=str(payload.email),
        password=payload.password,
    )
    if auth == "invalid":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if auth[0] == "account":
        account = auth[1]
        _set_account_session_cookie(response, account.id)
        return build_account_session_read(account)
    user = auth[1]
    _set_user_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/me/active-organization", response_model=UserRead)
def post_active_organization(
    payload: ActiveOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserRead:
    nxt = switch_membership_by_organization_slug(db, current=user, organization_slug=payload.organization_slug)
    if nxt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found or no access")
    _set_user_session_cookie(response, nxt.id)
    return build_user_read(db, nxt)


@router.post("/me/add-organization-membership", response_model=UserRead)
def post_add_organization_membership(
    payload: AddOrganizationMembershipInput,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserRead:
    try:
        new_membership = request_join_additional_organization(
            db,
            current_membership=user,
            organization_slug=payload.organization_slug,
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            message=payload.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, new_membership.id)
    return build_user_read(db, new_membership)


@router.post("/me/create-organization-membership", response_model=UserRead)
def post_create_organization_membership(
    payload: CreateOrganizationMembershipInput,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserRead:
    try:
        new_membership, _org = create_additional_organization_membership(
            db,
            current_membership=user,
            organization_name=payload.organization_name.strip(),
            organization_slug=payload.organization_slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, new_membership.id)
    return build_user_read(db, new_membership)


@router.post("/register", response_model=AccountSessionRead)
def post_register_account(
    payload: RegisterAccountInput,
    response: Response,
    db: Session = Depends(get_db),
) -> AccountSessionRead:
    try:
        acc = register_account_only(
            db,
            email=str(payload.email),
            password=payload.password,
            locale=payload.locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_account_session_cookie(response, acc.id)
    return build_account_session_read(acc)


@router.post("/me/onboarding/create-organization", response_model=UserRead)
def post_onboarding_create_organization(
    payload: OnboardingCreateOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_session),
) -> UserRead:
    try:
        user, _org = onboarding_create_organization(
            db,
            account=account,
            organization_name=payload.organization_name.strip(),
            organization_slug=payload.organization_slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/me/onboarding/join-organization", response_model=UserRead)
def post_onboarding_join_organization(
    payload: OnboardingJoinOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_session),
) -> UserRead:
    try:
        user, _org = onboarding_join_organization(
            db,
            account=account,
            organization_slug=payload.organization_slug,
            first_name=payload.first_name.strip(),
            last_name=payload.last_name.strip(),
            message=payload.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/register/create-organization", response_model=UserRead)
def post_register_create_organization(
    payload: RegisterCreateOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
) -> UserRead:
    try:
        user, _org = register_create_organization(
            db,
            organization_name=payload.organization_name,
            organization_slug=payload.organization_slug,
            email=str(payload.email),
            password=payload.password,
            locale=payload.locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/register/join-organization", response_model=UserRead)
def post_register_join_organization(
    payload: RegisterJoinOrganizationInput,
    response: Response,
    db: Session = Depends(get_db),
) -> UserRead:
    try:
        user, _org = register_join_organization(
            db,
            organization_slug=payload.organization_slug,
            email=str(payload.email),
            password=payload.password,
            first_name=payload.first_name,
            last_name=payload.last_name,
            message=payload.message,
            locale=payload.locale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    _clear_session_cookie(response)
    return {"ok": True}


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
def post_delete_account(
    payload: DeleteAccountInput,
    response: Response,
    db: Session = Depends(get_db),
    holder: User | Account = Depends(get_current_session_holder),
) -> None:
    account = holder if isinstance(holder, Account) else holder.account
    try:
        delete_own_account(db, account, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _clear_session_cookie(response)


@router.get("/me", response_model=AuthMeResponse)
def me(holder: User | Account = Depends(get_current_session_holder), db: Session = Depends(get_db)) -> UserRead | AccountSessionRead:
    if isinstance(holder, Account):
        return build_account_session_read(holder)
    return build_user_read(db, holder)


@router.get("/me/organization-invites", response_model=list[OrganizationMembershipInvitePendingRead])
def get_me_organization_invites(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[OrganizationMembershipInvitePendingRead]:
    rows = list_pending_invites_for_account(db, account_id=user.account_id)
    return [invite_pending_to_read(db, r) for r in rows]


@router.post("/me/organization-invites/{invite_id}/accept", response_model=UserRead)
def post_me_accept_organization_invite(
    invite_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    body: OrganizationInviteAcceptInput | None = Body(default=None),
) -> UserRead:
    try:
        new_user = accept_membership_invite(db, user=user, invite_id=invite_id, accept=body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    _set_user_session_cookie(response, new_user.id)
    return build_user_read(db, new_user)


@router.post("/me/organization-invites/{invite_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def post_me_decline_organization_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        decline_membership_invite(db, user=user, invite_id=invite_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/me/join-request", response_model=JoinRequestRead | None)
def get_me_join_request(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> JoinRequestRead | None:
    row = get_pending_join_request_for_user(db, user_id=user.id)
    if row is None:
        return None
    return join_request_to_read(row)


@router.post("/me/join-request", response_model=JoinRequestRead)
def post_me_join_request(
    payload: JoinRequestResubmitInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JoinRequestRead:
    if user.role != "applicant":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Applicant only")
    try:
        row = create_join_request_for_applicant(
            db,
            user=user,
            first_name=payload.first_name,
            last_name=payload.last_name,
            message=payload.message,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return join_request_to_read(row)


@router.get("/me/team-member", response_model=TeamMemberRead)
def get_me_team_member(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role != "team_member":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Team member role only")
    member = get_linked_team_member(db, user)
    if member is None:
        raise HTTPException(status_code=404, detail="No linked team member profile")
    db.refresh(member, attribute_names=["shift_group_links"])
    return team_member_to_read(member)


@router.patch("/me/team-member", response_model=TeamMemberRead)
def patch_me_team_member(
    payload: TeamMemberSelfUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "team_member":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Team member role only")
    try:
        member = update_self_team_member_profile(db, user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if member is None:
        raise HTTPException(status_code=404, detail="No linked team member profile")
    db.refresh(member, attribute_names=["shift_group_links"])
    return team_member_to_read(member)
