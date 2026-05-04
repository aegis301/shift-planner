"""invite precreated team member id

Revision ID: 202606020001
Revises: 202606010001
Create Date: 2026-06-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202606020001"
down_revision: Union[str, None] = "202606010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_membership_invites",
        sa.Column("precreated_team_member_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_org_membership_invites_precreated_team_member",
        "organization_membership_invites",
        "team_members",
        ["precreated_team_member_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_org_membership_invites_precreated_team_member", "organization_membership_invites", type_="foreignkey")
    op.drop_column("organization_membership_invites", "precreated_team_member_id")
