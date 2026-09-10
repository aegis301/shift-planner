"""contract groups, employment periods, opening balances

Revision ID: 202609100001
Revises: 202608270001
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.services.contract_employment_upgrade import apply_contract_employment_upgrade

revision: str = "202609100001"
down_revision: Union[str, None] = "202608270001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    apply_contract_employment_upgrade(op.get_bind())


def downgrade() -> None:
    raise NotImplementedError("Forward-only migration")
