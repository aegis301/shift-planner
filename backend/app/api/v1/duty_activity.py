from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planning_user, get_current_user
from app.db.session import get_db
from app.models import Organization, User
from app.schemas import (
    DutyActivityCreate,
    DutyActivityPurposeRead,
    DutyActivityUpdate,
    DutyUtilizationPeriodRead,
    DutyUtilizationSlotRead,
    TimeEntryRead,
)
from app.services.authz import (
    assert_duty_activity_individual_read,
    assert_planning_shift_group_scope,
    get_linked_team_member,
)
from app.services.duty_activity import (
    delete_duty_activity,
    duty_activity_to_read,
    list_duty_activity_episodes,
    record_duty_activity,
    update_duty_activity,
)
from app.services.duty_activity_privacy import (
    acknowledge_duty_activity_purpose,
    audit_duty_activity_read,
    read_duty_activity_purpose,
)
from app.services.duty_utilization import period_utilization, slot_utilization_for_assignee

router = APIRouter(prefix="/duty-activity", tags=["duty-activity"])


def _require_linked_member(db: Session, user: User):
    member = get_linked_team_member(db, user)
    if member is None:
        raise HTTPException(status_code=403, detail="Team member profile is not linked to this account")
    return member


def _require_purpose_acknowledged(member) -> None:
    if member.duty_activity_purpose_acknowledged_at is None:
        raise HTTPException(
            status_code=403,
            detail="Duty activity purpose must be acknowledged before recording",
        )


@router.get("/purpose", response_model=DutyActivityPurposeRead)
def get_duty_activity_purpose(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DutyActivityPurposeRead:
    member = _require_linked_member(db, user)
    org = db.get(Organization, user.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return read_duty_activity_purpose(org, member)


@router.post("/purpose/acknowledge", response_model=DutyActivityPurposeRead)
def post_duty_activity_purpose_acknowledge(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DutyActivityPurposeRead:
    member = _require_linked_member(db, user)
    return acknowledge_duty_activity_purpose(db, member, actor=user.email, source="rest")


@router.get("/utilization/{planning_period_id}", response_model=DutyUtilizationPeriodRead)
def get_duty_utilization(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    shift_template_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> DutyUtilizationPeriodRead:
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
        return period_utilization(
            db,
            organization_id=user.organization_id,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            shift_template_id=shift_template_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/slots/{roster_slot_id}/utilization", response_model=DutyUtilizationSlotRead)
def get_own_slot_duty_utilization(
    roster_slot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DutyUtilizationSlotRead:
    member = _require_linked_member(db, user)
    try:
        return slot_utilization_for_assignee(
            db,
            organization_id=user.organization_id,
            roster_slot_id=roster_slot_id,
            team_member_id=member.id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[TimeEntryRead])
def get_duty_activity_episodes(
    team_member_id: int | None = Query(default=None),
    roster_slot_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TimeEntryRead]:
    if team_member_id is None:
        target_id = _require_linked_member(db, user).id
    else:
        try:
            assert_duty_activity_individual_read(db, user, team_member_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        target_id = team_member_id
    rows = list_duty_activity_episodes(
        db,
        organization_id=user.organization_id,
        team_member_id=target_id,
        roster_slot_id=roster_slot_id,
    )
    audit_duty_activity_read(
        db,
        actor=user.email,
        source="rest",
        team_member_id=target_id,
        count=len(rows),
    )
    return [duty_activity_to_read(row) for row in rows]


@router.post("", response_model=TimeEntryRead)
def post_own_duty_activity(
    payload: DutyActivityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimeEntryRead:
    member = _require_linked_member(db, user)
    _require_purpose_acknowledged(member)
    if payload.team_member_id is not None and payload.team_member_id != member.id:
        raise HTTPException(status_code=403, detail="Can only record your own duty activity")
    try:
        row = record_duty_activity(
            db,
            payload,
            organization_id=user.organization_id,
            team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return duty_activity_to_read(row)


@router.patch("/{entry_id}", response_model=TimeEntryRead)
def patch_own_duty_activity(
    entry_id: int,
    payload: DutyActivityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TimeEntryRead:
    member = _require_linked_member(db, user)
    try:
        row = update_duty_activity(
            db,
            entry_id,
            payload,
            organization_id=user.organization_id,
            team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return duty_activity_to_read(row)


@router.delete("/{entry_id}")
def delete_own_duty_activity(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    member = _require_linked_member(db, user)
    try:
        deleted = delete_duty_activity(
            db,
            entry_id,
            organization_id=user.organization_id,
            team_member_id=member.id,
            actor=user.email,
            source="rest",
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Duty activity episode not found")
    return {"deleted": True}
