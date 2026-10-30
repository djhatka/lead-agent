"""dashboard language

Task 39: one switch to show every dashboard screen in Hindi. Stored per
business so it's remembered next time the owner logs in.

Revision ID: 2a6c9f0d3b5e
Revises: 9f3b6a1d4e82
Created: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = '2a6c9f0d3b5e'
down_revision = '9f3b6a1d4e82'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('language', sa.String(length=5), server_default='en', nullable=False))


def downgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('language')
