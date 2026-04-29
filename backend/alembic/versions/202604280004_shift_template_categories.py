"""normalize shift template categories

Revision ID: 202604280004
Revises: 202604280003
Create Date: 2026-04-28 00:04:00.000000
"""

from alembic import op


revision = "202604280004"
down_revision = "202604280003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE shift_templates
        SET category = CASE category
            WHEN 'on_call' THEN 'rufdienst'
            WHEN 'day' THEN 'other'
            WHEN 'night' THEN 'other'
            ELSE category
        END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE shift_templates
        SET category = CASE category
            WHEN 'rufdienst' THEN 'on_call'
            WHEN 'bereitschaftsdienst' THEN 'on_call'
            ELSE category
        END
        """
    )
