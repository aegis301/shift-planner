"""auth device sessions and refresh token history

Revision ID: 202609300001
Revises: 202609280001
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "202609300001"
down_revision: Union[str, None] = "202609280001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_device_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_auth_device_sessions_account_id", "auth_device_sessions", ["account_id"])
    op.create_index("ix_auth_device_sessions_user_id", "auth_device_sessions", ["user_id"])
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_session_id",
            sa.Integer(),
            sa.ForeignKey("auth_device_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_auth_refresh_tokens_device_session_id", "auth_refresh_tokens", ["device_session_id"])
    op.create_index("ix_auth_refresh_tokens_token_hash", "auth_refresh_tokens", ["token_hash"], unique=True)
    op.create_index(
        "uq_auth_refresh_tokens_one_current",
        "auth_refresh_tokens",
        ["device_session_id"],
        unique=True,
        postgresql_where=sa.text("rotated_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_auth_refresh_tokens_one_current", table_name="auth_refresh_tokens")
    op.drop_index("ix_auth_refresh_tokens_token_hash", table_name="auth_refresh_tokens")
    op.drop_index("ix_auth_refresh_tokens_device_session_id", table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
    op.drop_index("ix_auth_device_sessions_user_id", table_name="auth_device_sessions")
    op.drop_index("ix_auth_device_sessions_account_id", table_name="auth_device_sessions")
    op.drop_table("auth_device_sessions")
