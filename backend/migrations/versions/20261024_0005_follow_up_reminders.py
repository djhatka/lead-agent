"""follow-up reminders

Task 30: each business's follow-up choices (on/off, remind after how many days),
"remind me later" and "stop reminding me" on each lead, and a flag on each
message that says "this was a follow-up sent from a reminder".

Revision ID: 0005
Revises: 0004
Created: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('followup_settings', sa.JSON(), nullable=True))

    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('followup_snoozed_until', sa.DateTime(timezone=True), nullable=True))
        # server_default: every lead that already exists starts with reminders on
        batch_op.add_column(sa.Column('followup_stopped', sa.Boolean(), server_default=sa.false(), nullable=False))

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('followup', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('followup')

    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('followup_stopped')
        batch_op.drop_column('followup_snoozed_until')

    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('followup_settings')
