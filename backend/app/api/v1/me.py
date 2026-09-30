from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.file_responses import ICS_RESPONSES
from app.db.session import get_db
from app.models import User
from app.schemas import (
    DeletedFlagRead,
    HoursLedgerRead,
    MemberCalendarTokenRead,
    MemberDutyRead,
    MemberHomeRead,
    MemberSwapListItemRead,
    MemberWishesRead,
    PlanningCellBulkResult,
    PlanningCellBulkUpsert,
    PlanningCellClear,
    PlanningShiftIntentBulkUpsert,
    PlanningShiftIntentRead,
    TeamMemberPeriodNoteRead,
    TeamMemberPeriodNoteUpsert,
)
from app.services.member_portal import (
    MemberWishesForbidden,
    NoLinkedTeamMember,
    clear_calendar_token,
    clear_member_wishes_cells,
    get_member_home,
    get_member_hours,
    get_member_wishes,
    list_member_duties,
    list_member_swaps,
    member_calendar_ics,
    rotate_calendar_token,
    save_member_wishes_cells,
    save_member_wishes_intents,
    save_member_wishes_note,
)

router = APIRouter(prefix="/me", tags=["me"])


def _no_member(exc: NoLinkedTeamMember) -> HTTPException:
    return HTTPException(status_code=403, detail={"code": "no_linked_team_member", "message": "No linked team member profile"})


@router.get("/home", response_model=MemberHomeRead)
def get_home(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> MemberHomeRead:
    try:
        return MemberHomeRead.model_validate(get_member_home(db, user=user))
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc


@router.get("/duties", response_model=list[MemberDutyRead])
def get_duties(
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemberDutyRead]:
    try:
        return [MemberDutyRead.model_validate(row) for row in list_member_duties(db, user=user, start=start, end=end)]
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wishes/{planning_period_id}", response_model=MemberWishesRead)
def get_wishes(
    planning_period_id: int,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MemberWishesRead:
    try:
        return MemberWishesRead.model_validate(get_member_wishes(
            db, user=user, planning_period_id=planning_period_id, shift_group_id=shift_group_id
        ))
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except MemberWishesForbidden as exc:
        raise HTTPException(status_code=403, detail={"code": exc.reason}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/wishes/{planning_period_id}/cells", response_model=PlanningCellBulkResult)
def put_wishes_cells(
    planning_period_id: int,
    payload: PlanningCellBulkUpsert,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlanningCellBulkResult:
    try:
        return save_member_wishes_cells(
            db,
            user=user,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            payload=payload,
        )
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except MemberWishesForbidden as exc:
        raise HTTPException(status_code=403, detail={"code": exc.reason}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wishes/{planning_period_id}/cells/clear", response_model=DeletedFlagRead)
def post_wishes_cells_clear(
    planning_period_id: int,
    payload: PlanningCellClear,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DeletedFlagRead:
    try:
        cleared = clear_member_wishes_cells(
            db,
            user=user,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            payload=payload,
        )
        return DeletedFlagRead.model_validate(cleared)
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except MemberWishesForbidden as exc:
        raise HTTPException(status_code=403, detail={"code": exc.reason}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/wishes/{planning_period_id}/intents", response_model=list[PlanningShiftIntentRead])
def put_wishes_intents(
    planning_period_id: int,
    payload: PlanningShiftIntentBulkUpsert,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlanningShiftIntentRead]:
    try:
        return save_member_wishes_intents(
            db,
            user=user,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            payload=payload,
        )
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except MemberWishesForbidden as exc:
        raise HTTPException(status_code=403, detail={"code": exc.reason}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/wishes/{planning_period_id}/note", response_model=TeamMemberPeriodNoteRead)
def put_wishes_note(
    planning_period_id: int,
    payload: TeamMemberPeriodNoteUpsert,
    shift_group_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamMemberPeriodNoteRead:
    try:
        return save_member_wishes_note(
            db,
            user=user,
            planning_period_id=planning_period_id,
            shift_group_id=shift_group_id,
            payload=payload,
        )
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except MemberWishesForbidden as exc:
        raise HTTPException(status_code=403, detail={"code": exc.reason}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/swaps", response_model=list[MemberSwapListItemRead])
def get_swaps(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MemberSwapListItemRead]:
    try:
        return [MemberSwapListItemRead.model_validate(row) for row in list_member_swaps(db, user=user, status=status)]
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc


@router.get("/hours", response_model=HoursLedgerRead)
def get_hours(
    start: date = Query(alias="from"),
    end: date = Query(alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HoursLedgerRead:
    try:
        return get_member_hours(db, user=user, start=start, end=end)
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/calendar-token", response_model=MemberCalendarTokenRead)
def post_calendar_token(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> MemberCalendarTokenRead:
    try:
        token = rotate_calendar_token(db, user=user)
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc
    return MemberCalendarTokenRead(calendar_token=token)


@router.delete("/calendar-token", status_code=204)
def delete_calendar_token(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> None:
    try:
        clear_calendar_token(db, user=user)
    except NoLinkedTeamMember as exc:
        raise _no_member(exc) from exc


@router.get("/calendar.ics", response_class=Response, responses=ICS_RESPONSES)
def get_calendar_ics(token: str = Query(...), db: Session = Depends(get_db)) -> Response:
    try:
        body = member_calendar_ics(db, token=token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid calendar token") from exc
    return Response(content=body, media_type="text/calendar")
