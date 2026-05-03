import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import Account, TeamMember, User
from app.services.authz import ROLE_TEAM_MEMBER
from app.services.users import get_account_by_email, get_user_in_organization

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        members = list(
            db.scalars(
                select(TeamMember).where(TeamMember.user_id.is_(None), TeamMember.is_active.is_(True)).order_by(TeamMember.id)
            )
        )
        for member in members:
            email = member.email.lower()
            org_id = member.organization_id if member.organization_id is not None else settings.default_organization_id
            existing = get_user_in_organization(db, email, org_id)
            if existing is not None:
                log.info("skip team member id=%s email=%s (user email already exists)", member.id, email)
                continue
            acc = get_account_by_email(db, email)
            if acc is None:
                acc = Account(email=email, hashed_password=hash_password(settings.team_member_seed_password))
                db.add(acc)
                db.flush()
            user = User(account_id=acc.id, organization_id=org_id, role=ROLE_TEAM_MEMBER, locale="de")
            db.add(user)
            db.flush()
            member.user_id = user.id
            db.commit()
            log.info("linked team member id=%s to new user id=%s", member.id, user.id)


if __name__ == "__main__":
    main()
