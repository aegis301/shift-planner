from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import FairnessAccountsRead
from app.services.authz import assert_planning_shift_group_scope
from app.services.fairness import build_fairness_accounts

router = APIRouter(tags=["fairness"])


@router.get("/fairness/{planning_period_id}", response_model=FairnessAccountsRead)
def get_fairness_accounts(
    planning_period_id: int,
    shift_group_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> FairnessAccountsRead:
    try:
        assert_planning_shift_group_scope(db, user, shift_group_id)
        return build_fairness_accounts(
            db,
            planning_period_id,
            organization_id=user.organization_id,
            shift_group_id=shift_group_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
