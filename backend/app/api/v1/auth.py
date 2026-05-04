from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import SESSION_MAX_AGE_SECONDS, create_session_token
from app.db.session import get_db
from app.models import User
from app.schemas import (
    ActiveOrganizationInput,
    AddOrganizationMembershipInput,
    DeleteAccountInput,
    TeamMemberRead,
    TeamMemberSelfUpdate,
    JoinRequestRead,
    JoinRequestResubmitInput,
    LoginInput,
    RegisterCreateOrganizationInput,
    RegisterJoinOrganizationInput,
    UserRead,
)
from app.services.authz import get_linked_team_member
from app.services.team_members import team_member_to_read
from app.services.join_requests import (
    create_join_request_for_applicant,
    get_pending_join_request_for_user,
    join_request_to_read,
)
from app.services.registration import (
    register_create_organization,
    register_join_organization,
    request_join_additional_organization,
)
from app.services.users import (
    authenticate_login,
    build_user_read,
    delete_own_account,
    switch_membership_by_organization_slug,
    update_self_team_member_profile,
)


def _set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        "shift_planner_session",
        create_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
    )


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserRead)
def login(payload: LoginInput, response: Response, db: Session = Depends(get_db)) -> UserRead:
    outcome, user, org_choices = authenticate_login(
        db,
        email=str(payload.email),
        password=payload.password,
        organization_slug=payload.organization_slug,
    )
    if outcome == "organization_slug_required":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "organization_slug_required",
                "organizations": org_choices or [],
            },
        )
    if outcome != "success" or user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    _set_session_cookie(response, user.id)
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
    _set_session_cookie(response, nxt.id)
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
    _set_session_cookie(response, new_membership.id)
    return build_user_read(db, new_membership)


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
    _set_session_cookie(response, user.id)
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
    _set_session_cookie(response, user.id)
    return build_user_read(db, user)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("shift_planner_session")
    return {"ok": True}


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
def post_delete_account(
    payload: DeleteAccountInput,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        delete_own_account(db, user, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.delete_cookie("shift_planner_session")


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserRead:
    return build_user_read(db, user)


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
