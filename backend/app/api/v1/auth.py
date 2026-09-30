from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import (
    current_bearer_device_session_id,
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
    ChangePasswordInput,
    CreateOrganizationMembershipInput,
    DeleteAccountInput,
    DeviceSessionRead,
    JoinRequestRead,
    JoinRequestResubmitInput,
    LoginInput,
    OkFlagRead,
    OnboardingCreateOrganizationInput,
    OnboardingJoinOrganizationInput,
    OrganizationInviteAcceptInput,
    OrganizationMembershipInvitePendingRead,
    RegisterAccountInput,
    RegisterCreateOrganizationInput,
    RegisterJoinOrganizationInput,
    TeamMemberRead,
    TeamMemberSelfUpdate,
    TokenIssueInput,
    TokenPairRead,
    TokenRefreshInput,
    UserRead,
    UserReadWithAccessToken,
)
from app.services.authz import get_linked_team_member
from app.services.device_sessions import (
    REASON_CLIENT,
    REASON_USER,
    BearerRejected,
    RefreshRejected,
    authenticate_bearer,
    issue_device_session,
    list_device_sessions,
    refresh_device_session,
    reissue_access_token,
    revoke_device_session,
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
from app.services.registration import (
    create_additional_organization_membership,
    onboarding_create_organization,
    onboarding_join_organization,
    register_account_only,
    register_create_organization,
    register_join_organization,
    request_join_additional_organization,
)
from app.services.team_members import team_member_to_read
from app.services.users import (
    authenticate_login,
    build_account_session_read,
    build_user_read,
    change_own_account_password,
    delete_own_account,
    switch_membership_by_organization_slug,
    update_self_team_member_profile,
)


def _session_cookie_kwargs() -> dict[str, object]:
    kwargs: dict[str, object] = {
        "path": "/",
        "httponly": True,
        "samesite": "lax",
        "secure": settings.session_cookie_secure,
    }
    if settings.session_cookie_domain:
        kwargs["domain"] = settings.session_cookie_domain
    return kwargs


def _set_user_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        "shift_planner_session",
        create_user_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        **_session_cookie_kwargs(),
    )


def _set_account_session_cookie(response: Response, account_id: int) -> None:
    response.set_cookie(
        "shift_planner_session",
        create_account_session_token(account_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        **_session_cookie_kwargs(),
    )


def _user_json(read: UserRead, user_id: int, access_token: str | None = None) -> JSONResponse:
    payload = read.model_dump(mode="json")
    if access_token is not None:
        payload["access_token"] = access_token
    out = JSONResponse(content=payload)
    out.set_cookie(
        "shift_planner_session",
        create_user_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        **_session_cookie_kwargs(),
    )
    return out


def _bearer_access_for_user(db: Session, user: User, device_session_id: int | None) -> str | None:
    if device_session_id is None:
        return None
    try:
        return reissue_access_token(db, device_session_id=device_session_id, user=user)
    except BearerRejected as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session") from exc


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        "shift_planner_session",
        **_session_cookie_kwargs(),
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


@router.post("/token", response_model=TokenPairRead)
def post_token(payload: TokenIssueInput, db: Session = Depends(get_db)) -> TokenPairRead:
    auth = authenticate_login(db, email=str(payload.email), password=payload.password)
    if auth == "invalid":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if auth[0] == "account":
        account = auth[1]
        issued = issue_device_session(
            db, account=account, user=None, device_name=payload.device_name, platform=payload.platform
        )
        session = build_account_session_read(account)
    else:
        user = auth[1]
        issued = issue_device_session(
            db,
            account=user.account,
            user=user,
            device_name=payload.device_name,
            platform=payload.platform,
        )
        session = build_user_read(db, user)
    return TokenPairRead(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        session=session,
    )


@router.post("/token/refresh", response_model=TokenPairRead)
def post_token_refresh(payload: TokenRefreshInput, db: Session = Depends(get_db)) -> TokenPairRead:
    try:
        issued = refresh_device_session(db, payload.refresh_token)
    except RefreshRejected as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    holder, _device_session_id = authenticate_bearer(db, issued.access_token)
    if isinstance(holder, Account):
        session = build_account_session_read(holder)
    else:
        session = build_user_read(db, holder)
    return TokenPairRead(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        expires_in=issued.expires_in,
        session=session,
    )


@router.post("/token/revoke", status_code=status.HTTP_204_NO_CONTENT)
def post_token_revoke(
    db: Session = Depends(get_db),
    holder: User | Account = Depends(get_current_session_holder),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> None:
    if device_session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    account_id = holder.id if isinstance(holder, Account) else holder.account_id
    revoke_device_session(db, device_session_id=device_session_id, account_id=account_id, reason=REASON_CLIENT)


@router.get("/me/devices", response_model=list[DeviceSessionRead])
def get_me_devices(
    db: Session = Depends(get_db),
    holder: User | Account = Depends(get_current_session_holder),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> list[DeviceSessionRead]:
    account_id = holder.id if isinstance(holder, Account) else holder.account_id
    rows = list_device_sessions(
        db, account_id=account_id, current_device_session_id=device_session_id
    )
    return [DeviceSessionRead.model_validate(row, from_attributes=True) for row in rows]


@router.delete("/me/devices/{device_session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_me_device(
    device_session_id: int,
    db: Session = Depends(get_db),
    holder: User | Account = Depends(get_current_session_holder),
) -> None:
    account_id = holder.id if isinstance(holder, Account) else holder.account_id
    found = revoke_device_session(
        db, device_session_id=device_session_id, account_id=account_id, reason=REASON_USER
    )
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device session not found")


@router.post("/me/active-organization", response_model=UserReadWithAccessToken)
def post_active_organization(
    payload: ActiveOrganizationInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> JSONResponse:
    nxt = switch_membership_by_organization_slug(db, current=user, organization_slug=payload.organization_slug)
    if nxt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found or no access")
    access_token = _bearer_access_for_user(db, nxt, device_session_id)
    return _user_json(build_user_read(db, nxt), nxt.id, access_token)


@router.post("/me/add-organization-membership", response_model=UserReadWithAccessToken)
def post_add_organization_membership(
    payload: AddOrganizationMembershipInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> JSONResponse:
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
    access_token = _bearer_access_for_user(db, new_membership, device_session_id)
    return _user_json(build_user_read(db, new_membership), new_membership.id, access_token)


@router.post("/me/create-organization-membership", response_model=UserReadWithAccessToken)
def post_create_organization_membership(
    payload: CreateOrganizationMembershipInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> JSONResponse:
    try:
        new_membership, _org = create_additional_organization_membership(
            db,
            current_membership=user,
            organization_name=payload.organization_name.strip(),
            organization_slug=payload.organization_slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    access_token = _bearer_access_for_user(db, new_membership, device_session_id)
    return _user_json(build_user_read(db, new_membership), new_membership.id, access_token)


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


@router.post("/me/onboarding/create-organization", response_model=UserReadWithAccessToken)
def post_onboarding_create_organization(
    payload: OnboardingCreateOrganizationInput,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_session),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> JSONResponse:
    try:
        user, _org = onboarding_create_organization(
            db,
            account=account,
            organization_name=payload.organization_name.strip(),
            organization_slug=payload.organization_slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    access_token = _bearer_access_for_user(db, user, device_session_id)
    return _user_json(build_user_read(db, user), user.id, access_token)


@router.post("/me/onboarding/join-organization", response_model=UserReadWithAccessToken)
def post_onboarding_join_organization(
    payload: OnboardingJoinOrganizationInput,
    db: Session = Depends(get_db),
    account: Account = Depends(get_current_account_session),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> JSONResponse:
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
    access_token = _bearer_access_for_user(db, user, device_session_id)
    return _user_json(build_user_read(db, user), user.id, access_token)


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


@router.post("/logout", response_model=OkFlagRead)
def logout(response: Response) -> OkFlagRead:
    _clear_session_cookie(response)
    return OkFlagRead(ok=True)


@router.post("/me/change-password", status_code=status.HTTP_204_NO_CONTENT)
def post_change_password(
    payload: ChangePasswordInput,
    db: Session = Depends(get_db),
    holder: User | Account = Depends(get_current_session_holder),
) -> None:
    account = holder if isinstance(holder, Account) else holder.account
    try:
        change_own_account_password(
            db,
            account=account,
            current_password=payload.current_password,
            new_password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


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


@router.post("/me/organization-invites/{invite_id}/accept", response_model=UserReadWithAccessToken)
def post_me_accept_organization_invite(
    invite_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    body: OrganizationInviteAcceptInput | None = Body(default=None),
    device_session_id: int | None = Depends(current_bearer_device_session_id),
) -> JSONResponse:
    try:
        new_user = accept_membership_invite(db, user=user, invite_id=invite_id, accept=body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    access_token = _bearer_access_for_user(db, new_user, device_session_id)
    return _user_json(build_user_read(db, new_user), new_user.id, access_token)


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
    try:
        member = update_self_team_member_profile(db, user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if member is None:
        raise HTTPException(status_code=404, detail="No linked team member profile")
    db.refresh(member, attribute_names=["shift_group_links"])
    return team_member_to_read(member)
