"""instant AI first reply

Task 29: each business's auto-reply choices (off / always / only after hours,
opening hours, closed days, an optional note), and a flag on each message that
says "this reply was written and sent by the AI, not typed by the owner".

Revision ID: 0004
Revises: 0003
Created: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_reply_settings', sa.JSON(), nullable=True))

    with op.batch_alter_table('messages', schema=None) as batch_op:
        # server_default: every message that already exists is marked "not an auto-reply"
        batch_op.add_column(sa.Column('auto_reply', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_column('auto_reply')

    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('auto_reply_settings')
