from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Account,
    Organization,
    OrganizationJoinRequest,
    OrganizationMembershipInvite,
    PlanningPeriod,
    ShiftGroup,
    ShiftTemplate,
    TeamMember,
    User,
)
from app.services.audit import record_audit
from app.services.authz import is_admin
from app.services.planning import delete_planning_period
from app.services.shift_groups import delete_shift_group
from app.services.shift_templates import delete_shift_template
from app.services.team_members import delete_team_member


def delete_organization(db: Session, *, actor: User, confirm_organization_name: str) -> None:
    if not is_admin(actor):
        raise ValueError("Admin only")
    org = db.get(Organization, actor.organization_id)
    if org is None:
        raise ValueError("Organization not found")
    if org.name.strip() != confirm_organization_name.strip():
        raise ValueError("Organization name does not match")
    if org.id == settings.default_organization_id:
        raise ValueError("Cannot delete the default organization")
    org_id = org.id
    actor_label = actor.email
    period_ids = list(db.scalars(select(PlanningPeriod.id).where(PlanningPeriod.organization_id == org_id)))
    for pid in period_ids:
        delete_planning_period(db, pid, organization_id=org_id, actor=actor_label, source="rest")
    template_ids = list(db.scalars(select(ShiftTemplate.id).where(ShiftTemplate.organization_id == org_id)))
    for tid in template_ids:
        delete_shift_template(db, tid, organization_id=org_id, actor=actor_label, source="rest")
    group_ids = list(db.scalars(select(ShiftGroup.id).where(ShiftGroup.organization_id == org_id)))
    for gid in group_ids:
        delete_shift_group(db, gid, organization_id=org_id, actor=actor_label, source="rest")
    tm_ids = list(db.scalars(select(TeamMember.id).where(TeamMember.organization_id == org_id)))
    for tmid in tm_ids:
        delete_team_member(db, tmid, organization_id=org_id, actor=actor_label, source="rest")
    db.execute(delete(OrganizationMembershipInvite).where(OrganizationMembershipInvite.organization_id == org_id))
    db.execute(delete(OrganizationJoinRequest).where(OrganizationJoinRequest.organization_id == org_id))
    db.commit()
    users = list(db.scalars(select(User).where(User.organization_id == org_id)))
    for u in users:
        acc_id = u.account_id
        db.delete(u)
        db.flush()
        leftover = db.scalar(select(func.count()).select_from(User).where(User.account_id == acc_id)) or 0
        if leftover == 0:
            acc = db.get(Account, acc_id)
            if acc is not None:
                db.delete(acc)
    db.delete(org)
    record_audit(
        db,
        actor=actor_label,
        source="rest",
        action="delete_organization",
        entity_type="organization",
        entity_id=str(org_id),
        details={"organization_id": org_id},
    )
    db.commit()
