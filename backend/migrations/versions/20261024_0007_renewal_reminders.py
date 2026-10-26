"""renewal reminders

Task 32: memberships and services that are about to expire. The owner gets
a reminder with a ready message ("Priya's membership ends in 5 days") and
can renew or snooze it.

Revision ID: 0007
Revises: 0006
Created: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('renewals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=True),
    sa.Column('customer_name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('service', sa.String(length=100), nullable=False),
    sa.Column('expiry_date', sa.Date(), nullable=False),
    sa.Column('renewal_amount', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('renewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminders_sent', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_reminder_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('renewals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_renewals_business_id'), ['business_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_renewals_expiry_date'), ['expiry_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_renewals_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_renewals_status'), ['status'], unique=False)

    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('renewal_settings', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('renewal_settings')

    with op.batch_alter_table('renewals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_renewals_status'))
        batch_op.drop_index(batch_op.f('ix_renewals_lead_id'))
        batch_op.drop_index(batch_op.f('ix_renewals_expiry_date'))
        batch_op.drop_index(batch_op.f('ix_renewals_business_id'))

    op.drop_table('renewals')
