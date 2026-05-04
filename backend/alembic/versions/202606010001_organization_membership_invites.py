"""organization membership invites table

Revision ID: 202606010001
Revises: 202605050001
Create Date: 2026-06-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606010001"
down_revision: Union[str, None] = "202605050001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_membership_invites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invitee_account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("employment_percentage", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("team_member_shift_group_ids", sa.JSON(), nullable=True),
        sa.Column("planner_shift_group_ids", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_organization_membership_invites_org",
        "organization_membership_invites",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_membership_invites_account",
        "organization_membership_invites",
        ["invitee_account_id"],
    )
    op.create_index(
        "ix_organization_membership_invites_invited_by",
        "organization_membership_invites",
        ["invited_by_user_id"],
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_org_membership_invite_pending_account
        ON organization_membership_invites (organization_id, invitee_account_id)
        WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_org_membership_invite_pending_account")
    op.drop_table("organization_membership_invites")
