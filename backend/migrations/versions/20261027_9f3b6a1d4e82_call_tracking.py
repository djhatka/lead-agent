"""call tracking

Task 38: a phone tracking number per business - calls recorded, missed calls
flagged for a call-back, the AI notes what was asked (when a transcript is
available).

Revision ID: 9f3b6a1d4e82
Revises: 7d2e4c8a1f6b
Created: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = '9f3b6a1d4e82'
down_revision = '7d2e4c8a1f6b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tracking_numbers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.String(length=20), nullable=False),
    sa.Column('provider_sid', sa.String(length=60), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('tracking_numbers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tracking_numbers_business_id'), ['business_id'], unique=True)

    op.create_table('calls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('external_id', sa.String(length=100), nullable=False),
    sa.Column('from_number', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('duration_seconds', sa.Integer(), server_default='0', nullable=False),
    sa.Column('recording_url', sa.String(length=500), nullable=False),
    sa.Column('transcript', sa.Text(), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('called_back_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'external_id', name='uq_call_business_external'),
    )
    with op.batch_alter_table('calls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_calls_business_id'), ['business_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_calls_started_at'), ['started_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('calls', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_calls_started_at'))
        batch_op.drop_index(batch_op.f('ix_calls_status'))
        batch_op.drop_index(batch_op.f('ix_calls_business_id'))
    op.drop_table('calls')

    with op.batch_alter_table('tracking_numbers', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tracking_numbers_business_id'))
    op.drop_table('tracking_numbers')
