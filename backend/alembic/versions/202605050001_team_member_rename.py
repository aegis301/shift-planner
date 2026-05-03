"""rename doctors to team_members and related columns

Revision ID: 202605050001
Revises: 202605040001
Create Date: 2026-05-05
"""

from typing import Sequence, Union

from alembic import op

revision: str = "202605050001"
down_revision: Union[str, None] = "202605040001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE doctors RENAME TO team_members")
    op.execute("ALTER INDEX IF EXISTS ix_doctors_org_email RENAME TO ix_team_members_org_email")
    op.execute("ALTER INDEX IF EXISTS ix_doctors_user_id RENAME TO ix_team_members_user_id")
    op.execute("ALTER TABLE doctor_shift_groups RENAME TO team_member_shift_groups")
    op.execute("ALTER TABLE team_member_shift_groups RENAME COLUMN doctor_id TO team_member_id")
    op.execute("ALTER TABLE planning_cells RENAME COLUMN doctor_id TO team_member_id")
    op.execute("ALTER TABLE roster_slot_assignments RENAME COLUMN doctor_id TO team_member_id")
    op.execute("ALTER TABLE planning_shift_intents RENAME COLUMN doctor_id TO team_member_id")
    op.execute("ALTER TABLE organization_join_requests RENAME COLUMN resolved_doctor_id TO resolved_team_member_id")
    op.execute("ALTER TABLE doctor_period_notes RENAME TO team_member_period_notes")
    op.execute("ALTER TABLE team_member_period_notes RENAME COLUMN doctor_id TO team_member_id")
    op.execute("UPDATE users SET role = 'team_member' WHERE role = 'doctor'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'doctor' WHERE role = 'team_member'")
    op.execute("ALTER TABLE team_member_period_notes RENAME COLUMN team_member_id TO doctor_id")
    op.execute("ALTER TABLE team_member_period_notes RENAME TO doctor_period_notes")
    op.execute("ALTER TABLE organization_join_requests RENAME COLUMN resolved_team_member_id TO resolved_doctor_id")
    op.execute("ALTER TABLE planning_shift_intents RENAME COLUMN team_member_id TO doctor_id")
    op.execute("ALTER TABLE roster_slot_assignments RENAME COLUMN team_member_id TO doctor_id")
    op.execute("ALTER TABLE planning_cells RENAME COLUMN team_member_id TO doctor_id")
    op.execute("ALTER TABLE team_member_shift_groups RENAME COLUMN team_member_id TO doctor_id")
    op.execute("ALTER TABLE team_member_shift_groups RENAME TO doctor_shift_groups")
    op.execute("ALTER INDEX IF EXISTS ix_team_members_user_id RENAME TO ix_doctors_user_id")
    op.execute("ALTER INDEX IF EXISTS ix_team_members_org_email RENAME TO ix_doctors_org_email")
    op.execute("ALTER TABLE team_members RENAME TO doctors")
