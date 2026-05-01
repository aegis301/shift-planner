from fastapi import APIRouter

from app.api.v1 import (
    auth,
    doctors,
    matrix,
    organization_admin,
    organizations_public,
    planning,
    roster_matrix,
    shift_groups,
    shift_templates,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations_public.router)
api_router.include_router(organization_admin.router)
api_router.include_router(doctors.router)
api_router.include_router(shift_groups.router)
api_router.include_router(shift_templates.router)
api_router.include_router(planning.router)
api_router.include_router(matrix.router)
api_router.include_router(roster_matrix.router)
