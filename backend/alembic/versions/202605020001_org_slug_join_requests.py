"""organization slug, per-org user email unique, join requests

Revision ID: 202605020001
Revises: 202605010001
Create Date: 2026-05-02
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "202605020001"
down_revision: Union[str, None] = "202605010001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_users_global_email_unique() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    for uc in insp.get_unique_constraints("users") or []:
        if list(uc.get("column_names") or []) == ["email"]:
            op.drop_constraint(uc["name"], "users", type_="unique")
            return
    for ix in insp.get_indexes("users") or []:
        if ix.get("unique") and list(ix.get("column_names") or []) == ["email"]:
            op.drop_index(ix["name"], table_name="users")
            return
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_users_email"))


def upgrade() -> None:
    op.add_column("organizations", sa.Column("slug", sa.String(length=64), nullable=True))
    op.execute(sa.text("UPDATE organizations SET slug = 'org-' || id::text WHERE slug IS NULL"))
    op.execute(sa.text("UPDATE organizations SET slug = 'default' WHERE id = 1"))
    op.alter_column("organizations", "slug", nullable=False)
    op.create_index("ix_organizations_slug", "organizations", ["slug"], unique=True)

    _drop_users_global_email_unique()
    op.create_index("ix_users_org_email", "users", ["organization_id", "email"], unique=True)

    op.create_table(
        "organization_join_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("requester_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.Column("resolved_doctor_id", sa.Integer(), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_org_join_requests_org_status",
        "organization_join_requests",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_org_join_requests_org_status", table_name="organization_join_requests")
    op.drop_table("organization_join_requests")

    op.drop_index("ix_users_org_email", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])

    op.drop_index("ix_organizations_slug", table_name="organizations")
    op.drop_column("organizations", "slug")
