"""work time consent register

Revision ID: 202609110001
Revises: 202609100005
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609110001"
down_revision: Union[str, None] = "202609100005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_time_consents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_member_id", sa.Integer(), sa.ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_type", sa.String(length=32), nullable=False, server_default="opt_out"),
        sa.Column("tier", sa.String(length=64), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("signed_document_reference", sa.String(length=255), nullable=True),
        sa.Column("recorded_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.Date(), nullable=True),
        sa.Column("notice_period_months", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("effective_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_work_time_consents_organization_id", "work_time_consents", ["organization_id"])
    op.create_index("ix_work_time_consents_team_member_id", "work_time_consents", ["team_member_id"])
    op.create_index("ix_work_time_consents_member_valid_from", "work_time_consents", ["team_member_id", "valid_from"])


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
