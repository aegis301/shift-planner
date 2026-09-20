from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_planning_user
from app.db.session import get_db
from app.models import User
from app.schemas import ContractGroupCreate, ContractGroupRead, ContractGroupUpdate
from app.services.contract_groups import (
    contract_group_to_read,
    create_contract_group,
    delete_contract_group,
    ensure_default_contract_group,
    list_contract_groups,
    update_contract_group,
)

router = APIRouter(prefix="/contract-groups", tags=["contract-groups"])


@router.get("", response_model=list[ContractGroupRead])
def get_contract_groups(
    active_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_planning_user),
) -> list[ContractGroupRead]:
    ensure_default_contract_group(db, organization_id=user.organization_id)
    db.commit()
    rows = list_contract_groups(db, organization_id=user.organization_id, active_only=active_only)
    return [contract_group_to_read(row) for row in rows]


@router.post("", response_model=ContractGroupRead, status_code=status.HTTP_201_CREATED)
def post_contract_group(
    payload: ContractGroupCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> ContractGroupRead:
    try:
        row = create_contract_group(
            db, payload, organization_id=user.organization_id, actor=user.email, source="rest"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return contract_group_to_read(row)


@router.patch("/{contract_group_id}", response_model=ContractGroupRead)
def patch_contract_group(
    contract_group_id: int,
    payload: ContractGroupUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> ContractGroupRead:
    try:
        row = update_contract_group(
            db,
            contract_group_id,
            payload,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Contract group not found")
    return contract_group_to_read(row)


@router.delete("/{contract_group_id}")
def delete_contract_group_endpoint(
    contract_group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_admin),
) -> dict[str, bool]:
    try:
        deleted = delete_contract_group(
            db,
            contract_group_id,
            organization_id=user.organization_id,
            actor=user.email,
            source="rest",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Contract group not found")
    return {"deleted": True}
