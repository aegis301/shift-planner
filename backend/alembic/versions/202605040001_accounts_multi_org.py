"""accounts table; users become org memberships per account

Revision ID: 202605040001
Revises: 202605020001
Create Date: 2026-05-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "202605040001"
down_revision: Union[str, None] = "202605020001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_users_org_email_uniqueness() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    for ix in insp.get_indexes("users") or []:
        if ix.get("unique") and list(ix.get("column_names") or []) == ["organization_id", "email"]:
            op.drop_index(ix["name"], table_name="users")
            return
    for uc in insp.get_unique_constraints("users") or []:
        if list(uc.get("column_names") or []) == ["organization_id", "email"]:
            op.drop_constraint(uc["name"], "users", type_="unique")
            return
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_users_org_email"))
        op.execute(sa.text('ALTER TABLE users DROP CONSTRAINT IF EXISTS "uq_users_organization_email"'))
    else:
        op.execute(sa.text("DROP INDEX IF EXISTS ix_users_org_email"))


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_email", "accounts", ["email"], unique=True)

    op.execute(
        sa.text(
            """
            INSERT INTO accounts (email, hashed_password, created_at)
            SELECT lower(trim(u.email)), MIN(u.hashed_password), now()
            FROM users u
            GROUP BY lower(trim(u.email))
            """
        )
    )

    op.add_column("users", sa.Column("account_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE users AS u
            SET account_id = a.id
            FROM accounts AS a
            WHERE a.email = lower(trim(u.email))
            """
        )
    )
    op.alter_column("users", "account_id", nullable=False)
    op.create_foreign_key(
        "fk_users_account_id",
        "users",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_users_account_id", "users", ["account_id"], unique=False)

    _drop_users_org_email_uniqueness()
    op.create_unique_constraint("uq_user_account_organization", "users", ["account_id", "organization_id"])

    op.drop_column("users", "hashed_password")
    op.drop_column("users", "email")


def downgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE users AS u
            SET email = a.email,
                hashed_password = a.hashed_password
            FROM accounts AS a
            WHERE u.account_id = a.id
            """
        )
    )
    op.alter_column("users", "email", nullable=False)
    op.alter_column("users", "hashed_password", nullable=False)

    op.drop_constraint("uq_user_account_organization", "users", type_="unique")
    op.create_index("ix_users_org_email", "users", ["organization_id", "email"], unique=True)

    op.drop_index("ix_users_account_id", table_name="users")
    op.drop_constraint("fk_users_account_id", "users", type_="foreignkey")
    op.drop_column("users", "account_id")

    op.drop_index("ix_accounts_email", table_name="accounts")
    op.drop_table("accounts")
