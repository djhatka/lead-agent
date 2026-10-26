"""payments and dues

Task 31: money customers owe the business (advances, fees), each with its own
payment page (/pay/<token>) that pays the owner's UPI ID directly; and each
business's payment choices (UPI ID, name shown to customers, automatic reminders).

Revision ID: 0006
Revises: 0005
Created: 2026-10-24
"""

from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('dues',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('lead_id', sa.Integer(), nullable=True),
    sa.Column('customer_name', sa.String(length=100), nullable=False),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('purpose', sa.String(length=200), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('token', sa.String(length=32), nullable=False),
    sa.Column('customer_says_paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('paid_via', sa.String(length=12), nullable=False),
    sa.Column('auto_remind', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('reminders_sent', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_reminder_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    with op.batch_alter_table('dues', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dues_business_id'), ['business_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dues_lead_id'), ['lead_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_dues_paid_at'), ['paid_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_dues_status'), ['status'], unique=False)

    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('payment_settings', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('payment_settings')

    with op.batch_alter_table('dues', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dues_status'))
        batch_op.drop_index(batch_op.f('ix_dues_paid_at'))
        batch_op.drop_index(batch_op.f('ix_dues_lead_id'))
        batch_op.drop_index(batch_op.f('ix_dues_business_id'))

    op.drop_table('dues')
