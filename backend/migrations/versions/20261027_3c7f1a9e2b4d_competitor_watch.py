"""competitor watch

Task 35: 3-5 nearby rivals the owner watches (rating, reviews), plus one
"they moved" alert per noticed change.

Revision ID: 3c7f1a9e2b4d
Revises: 1fa9e753c1f6
Created: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = '3c7f1a9e2b4d'
down_revision = '1fa9e753c1f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('competitors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('area', sa.String(length=100), nullable=False),
    sa.Column('place_id', sa.String(length=150), nullable=True),
    sa.Column('rating', sa.Float(), nullable=True),
    sa.Column('review_count', sa.Integer(), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=False),
    sa.Column('address', sa.String(length=300), nullable=False),
    sa.Column('previous_rating', sa.Float(), nullable=True),
    sa.Column('previous_review_count', sa.Integer(), nullable=True),
    sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('problem', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('business_id', 'name', 'area', name='uq_competitor_business_name_area'),
    )
    with op.batch_alter_table('competitors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competitors_business_id'), ['business_id'], unique=False)

    op.create_table('competitor_alerts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('business_id', sa.Integer(), nullable=False),
    sa.Column('competitor_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['competitor_id'], ['competitors.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('competitor_alerts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_competitor_alerts_business_id'), ['business_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_competitor_alerts_competitor_id'), ['competitor_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_competitor_alerts_created_at'), ['created_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('competitor_alerts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competitor_alerts_created_at'))
        batch_op.drop_index(batch_op.f('ix_competitor_alerts_competitor_id'))
        batch_op.drop_index(batch_op.f('ix_competitor_alerts_business_id'))
    op.drop_table('competitor_alerts')

    with op.batch_alter_table('competitors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_competitors_business_id'))
    op.drop_table('competitors')
