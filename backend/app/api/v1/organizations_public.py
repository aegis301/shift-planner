from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import OrganizationLookupResponse
from app.services.organizations import get_organization_by_slug

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/lookup", response_model=OrganizationLookupResponse)
def lookup_organization(
    slug: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
) -> OrganizationLookupResponse:
    org = get_organization_by_slug(db, slug)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return OrganizationLookupResponse(slug=org.slug, name=org.name)
