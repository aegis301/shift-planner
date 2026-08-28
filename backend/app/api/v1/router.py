from fastapi import APIRouter

from app.api.v1 import (
    auth,
    dashboard,
    matrix,
    organization_admin,
    organizations_public,
    planning,
    planning_day_status_definitions,
    roster_matrix,
    shift_groups,
    shift_templates,
    team_member_property_definitions,
    team_member_property_matrix,
    team_members,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(organizations_public.router)
api_router.include_router(organization_admin.router)
api_router.include_router(team_members.router)
api_router.include_router(team_member_property_definitions.router)
api_router.include_router(team_member_property_matrix.router)
api_router.include_router(planning_day_status_definitions.router)
api_router.include_router(shift_groups.router)
api_router.include_router(shift_templates.router)
api_router.include_router(planning.router)
api_router.include_router(dashboard.router)
api_router.include_router(matrix.router)
api_router.include_router(roster_matrix.router)
api_router.include_router(roster_matrix.export_router)
