"""fact check

Revision ID: a1b2c3d4e5f6
Revises: 880562e611cd
Create Date: 2026-10-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '880562e611cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('fact_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('category', sa.String(length=32), nullable=False),
    sa.Column('subject', sa.String(length=128), nullable=False),
    sa.Column('correct_claim', sa.String(length=1000), nullable=False),
    sa.Column('source_ref', sa.String(length=500), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version', 'code'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    with op.batch_alter_table('fact_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fact_items_version'), ['version'], unique=False)

    op.create_table('fact_claims',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=128), nullable=False),
    sa.Column('extract_version', sa.Integer(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('sentence', sa.String(length=2000), nullable=False),
    sa.Column('fact_code', sa.String(length=32), nullable=True),
    sa.Column('raw_label', sa.String(length=32), nullable=False),
    sa.Column('reviewer_decision', sa.String(length=16), server_default='pending', nullable=False),
    sa.Column('reviewed_at', app.models.CSTDateTime(), nullable=True),
    sa.Column('reviewed_by', sa.String(length=64), nullable=True),
    sa.Column('note', sa.String(length=500), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    with op.batch_alter_table('fact_claims', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fact_claims_run_id'), ['run_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('fact_claims')
    op.drop_table('fact_items')
