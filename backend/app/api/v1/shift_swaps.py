from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planner, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import (
    ShiftSwapApplyRead,
    ShiftSwapRequestCreate,
    ShiftSwapRequestRead,
    ShiftSwapUnresolvedRead,
)
from app.services.authz import (
    assert_planning_shift_group_scope,
    can_use_planning_ui,
    get_linked_team_member,
    is_admin,
    planner_shift_group_ids,
)
from app.services.shift_swaps import (
    ShiftSwapConflictError,
    ShiftSwapNotFoundError,
    accept_shift_swap,
    applied_swap_to_read,
    apply_shift_swap,
    approve_shift_swap,
    claim_shift_swap,
    create_shift_swap,
    eligible_member_ids_for_request,
    get_shift_swap,
    list_eligible_claimants,
    list_shift_swaps,
    list_unresolved_shift_swaps,
    open_shift_swap,
    reject_shift_swap,
    shift_swap_to_read,
    withdraw_shift_swap,
)

router = APIRouter(prefix="/shift-swaps", tags=["shift-swaps"])


def _http_conflict(exc: ShiftSwapConflictError) -> HTTPException:
    detail: dict = {"code": exc.code, "message": exc.message}
    if exc.findings:
        detail["findings"] = [row.model_dump(mode="json") for row in exc.findings]
    return HTTPException(status_code=409, detail=detail)


def _linked_member(db: Session, user: User):
    member = get_linked_team_member(db, user)
    if member is None:
        raise HTTPException(status_code=403, detail="Team member profile is not linked to this account")
    return member


def _assert_planner_scope(db: Session, user: User, shift_group_id: int) -> None:
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


def _can_view(db: Session, user: User, row) -> None:
    if is_admin(user):
        return
    if can_use_planning_ui(user):
        _assert_planner_scope(db, user, row.shift_group_id)
        return
    member = _linked_member(db, user)
    if row.offered_by_team_member_id == member.id or row.target_team_member_id == member.id:
        return
    visible = list_shift_swaps(
        db,
        organization_id=user.organization_id,
        planning_period_id=row.planning_period_id,
        shift_group_id=row.shift_group_id,
        viewer_team_member_id=member.id,
    )
    if any(item.id == row.id for item in visible):
        return
    raise HTTPException(status_code=403, detail="Not allowed to view this swap request")


def _to_read(db, row) -> ShiftSwapRequestRead:
    return shift_swap_to_read(row, eligible_member_ids=eligible_member_ids_for_request(db, row))


@router.get("/eligible-members", response_model=list[int])
def get_eligible_members(
    roster_slot_id: int = Query(...),
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[int]:
    exclude_id = None
    if can_use_planning_ui(user):
        if shift_group_id is not None:
            _assert_planner_scope(db, user, shift_group_id)
    else:
        member = _linked_member(db, user)
        exclude_id = member.id
    try:
        return list_eligible_claimants(
            db,
            roster_slot_id=roster_slot_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
            exclude_team_member_id=exclude_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[ShiftSwapRequestRead])
def get_shift_swaps(
    planning_period_id: int = Query(...),
    shift_group_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ShiftSwapRequestRead]:
    viewer_team_member_id = None
    planner_ids = None
    if is_admin(user):
        pass
    elif can_use_planning_ui(user):
        if shift_group_id is not None:
            _assert_planner_scope(db, user, shift_group_id)
        else:
            planner_ids = planner_shift_group_ids(db, user)
    else:
        member = _linked_member(db, user)
        viewer_team_member_id = member.id
        if shift_group_id is None:
            raise HTTPException(status_code=400, detail="shift_group_id is required")
    try:
        rows = list_shift_swaps(
            db,
            organization_id=user.organization_id,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            status=status,
            statuses=statuses,
            kind=kind,
            viewer_team_member_id=viewer_team_member_id,
            planner_shift_group_ids=planner_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_to_read(db, row) for row in rows]


@router.get("/unresolved", response_model=list[ShiftSwapUnresolvedRead])
def get_unresolved_shift_swaps(
    planning_period_id: int = Query(...),
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> list[ShiftSwapUnresolvedRead]:
    _assert_planner_scope(db, user, shift_group_id)
    try:
        return list_unresolved_shift_swaps(
            db,
            organization_id=user.organization_id,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            planner_shift_group_ids=None if is_admin(user) else planner_shift_group_ids(db, user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=ShiftSwapRequestRead)
def post_shift_swap(
    payload: ShiftSwapRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    member = _linked_member(db, user)
    try:
        row = create_shift_swap(
            db,
            payload,
            organization_id=user.organization_id,
            offered_by_team_member_id=member.id,
            actor=user.email,
            source="rest",
            created_by_user_id=user.id,
        )
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_read(db, row)


@router.get("/{request_id}", response_model=ShiftSwapRequestRead)
def get_shift_swap_endpoint(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    try:
        row = get_shift_swap(db, request_id, organization_id=user.organization_id)
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _can_view(db, user, row)
    return _to_read(db, row)


@router.post("/{request_id}/open", response_model=ShiftSwapRequestRead)
def post_open_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    member = _linked_member(db, user)
    try:
        row = open_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            actor_team_member_id=member.id,
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/claim", response_model=ShiftSwapRequestRead)
def post_claim_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    member = _linked_member(db, user)
    try:
        row = claim_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            claimer_team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/accept", response_model=ShiftSwapRequestRead)
def post_accept_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    member = _linked_member(db, user)
    try:
        row = accept_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            actor_team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/decline", response_model=ShiftSwapRequestRead)
def post_decline_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    member = _linked_member(db, user)
    try:
        row = reject_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            resolved_by_user_id=user.id,
            actor_team_member_id=member.id,
            allow_planner=False,
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/withdraw", response_model=ShiftSwapRequestRead)
def post_withdraw_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShiftSwapRequestRead:
    try:
        existing = get_shift_swap(db, request_id, organization_id=user.organization_id)
        if can_use_planning_ui(user):
            _assert_planner_scope(db, user, existing.shift_group_id)
            row = withdraw_shift_swap(
                db,
                request_id,
                organization_id=user.organization_id,
                actor_team_member_id=None,
                actor=user.email,
                source="rest",
                allow_planner=True,
            )
        else:
            member = _linked_member(db, user)
            row = withdraw_shift_swap(
                db,
                request_id,
                organization_id=user.organization_id,
                actor_team_member_id=member.id,
                actor=user.email,
                source="rest",
            )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/approve", response_model=ShiftSwapRequestRead)
def post_approve_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> ShiftSwapRequestRead:
    try:
        existing = get_shift_swap(db, request_id, organization_id=user.organization_id)
        _assert_planner_scope(db, user, existing.shift_group_id)
        row = approve_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            resolved_by_user_id=user.id,
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/reject", response_model=ShiftSwapRequestRead)
def post_reject_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> ShiftSwapRequestRead:
    try:
        existing = get_shift_swap(db, request_id, organization_id=user.organization_id)
        _assert_planner_scope(db, user, existing.shift_group_id)
        row = reject_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            resolved_by_user_id=user.id,
            allow_planner=True,
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _to_read(db, row)


@router.post("/{request_id}/apply", response_model=ShiftSwapApplyRead)
def post_apply_shift_swap(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planner),
) -> ShiftSwapApplyRead:
    try:
        existing = get_shift_swap(db, request_id, organization_id=user.organization_id)
        _assert_planner_scope(db, user, existing.shift_group_id)
        row, assignments, version = apply_shift_swap(
            db,
            request_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
            applied_by_user_id=user.id,
        )
    except ShiftSwapNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShiftSwapConflictError as exc:
        raise _http_conflict(exc) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return applied_swap_to_read(row, assignments, version)
