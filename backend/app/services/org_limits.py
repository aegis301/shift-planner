from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Organization, TeamMember


def assert_org_allows_team_member_user_link(db: Session, org: Organization) -> None:
    if org.seat_limit is None:
        return
    linked = (
        db.scalar(
            select(func.count())
            .select_from(TeamMember)
            .where(TeamMember.organization_id == org.id, TeamMember.user_id.is_not(None))
        )
        or 0
    )
    if linked >= org.seat_limit:
        raise ValueError("Organization seat limit for linked team member accounts reached")
