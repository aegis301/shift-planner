from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, TeamMember, User
from app.schemas.domain import OrganizationStaffDirectoryRow, StaffDirectoryLinkStatus


def _norm_email(value: str) -> str:
    return value.strip().lower()


def list_organization_staff_directory(db: Session, *, organization_id: int) -> list[OrganizationStaffDirectoryRow]:
    team_members = list(
        db.scalars(
            select(TeamMember).where(TeamMember.organization_id == organization_id).order_by(TeamMember.email, TeamMember.id)
        ).all()
    )
    users = list(
        db.scalars(
            select(User)
            .join(Account, Account.id == User.account_id)
            .where(User.organization_id == organization_id)
            .order_by(Account.email, User.id)
        ).all()
    )
    users_by_norm: dict[str, User] = {}
    for u in users:
        key = _norm_email(u.email)
        users_by_norm[key] = u

    team_member_norm_keys: set[str] = {_norm_email(d.email) for d in team_members}
    rows: list[OrganizationStaffDirectoryRow] = []

    for d in team_members:
        ne = _norm_email(d.email)
        label = f"{d.last_name}, {d.first_name}"
        user_match = users_by_norm.get(ne)
        linked: User | None = db.get(User, d.user_id) if d.user_id is not None else None
        status: StaffDirectoryLinkStatus
        if user_match is None and linked is None:
            status = "team_member_only"
        elif user_match is None and linked is not None:
            status = "linked_foreign_user"
        elif user_match is not None and linked is None:
            status = "login_unlinked"
        elif user_match is not None and linked is not None and linked.id == user_match.id:
            status = "linked_ok"
        else:
            status = "linked_wrong_user"

        rows.append(
            OrganizationStaffDirectoryRow(
                email=d.email,
                team_member_id=d.id,
                team_member_label=label,
                team_member_is_active=d.is_active,
                user_id=user_match.id if user_match is not None else None,
                user_role=user_match.role if user_match is not None else None,
                user_is_active=user_match.is_active if user_match is not None else None,
                linked_user_id=d.user_id,
                linked_user_role=linked.role if linked is not None else None,
                linked_user_is_active=linked.is_active if linked is not None else None,
                link_status=status,
            )
        )

    for u in users:
        ne = _norm_email(u.email)
        if ne in team_member_norm_keys:
            continue
        rows.append(
            OrganizationStaffDirectoryRow(
                email=u.email,
                team_member_id=None,
                team_member_label=None,
                team_member_is_active=None,
                user_id=u.id,
                user_role=u.role,
                user_is_active=u.is_active,
                linked_user_id=None,
                linked_user_role=None,
                linked_user_is_active=None,
                link_status="login_only",
            )
        )

    rows.sort(key=lambda r: (_norm_email(r.email), r.team_member_id or 0, r.user_id or 0))
    return rows
