"""brand marks

Revision ID: 326cd29287b6
Revises: 47703f934f0f
Create Date: 2026-10-22 18:35:02.053214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = '326cd29287b6'
down_revision: Union[str, Sequence[str], None] = '47703f934f0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('brand_marks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('value', sa.String(length=128).with_variant(mysql.VARCHAR(collation='utf8mb4_bin', length=128), 'mysql'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version', 'kind', 'value'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    with op.batch_alter_table('brand_marks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_brand_marks_version'), ['version'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('brand_marks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_brand_marks_version'))
    op.drop_table('brand_marks')
