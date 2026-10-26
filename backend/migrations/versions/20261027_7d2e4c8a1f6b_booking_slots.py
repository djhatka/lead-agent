"""booking slots

Task 37: a customer picks a free time slot themselves, through a shareable
link the owner sends from WhatsApp - no back-and-forth needed.

Revision ID: 7d2e4c8a1f6b
Revises: 3c7f1a9e2b4d
Created: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = '7d2e4c8a1f6b'
down_revision = '3c7f1a9e2b4d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('booking_settings', sa.JSON(), nullable=True))

    op.create_table('bookings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=True),
    sa.Column('customer_name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('service', sa.String(length=150), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('token', sa.String(length=32), nullable=False),
    sa.Column('slot_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_minutes', sa.Integer(), server_default='30', nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token'),
    )
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bookings_business_id'), ['business_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_slot_at'), ['slot_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_slot_at'))
        batch_op.drop_index(batch_op.f('ix_bookings_status'))
        batch_op.drop_index(batch_op.f('ix_bookings_lead_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_business_id'))
    op.drop_table('bookings')

    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('booking_settings')
