"""knowledge base

Revision ID: 880562e611cd
Revises: b568b2ebfe8f
Create Date: 2026-10-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
import app.models


# revision identifiers, used by Alembic.
revision: str = '880562e611cd'
down_revision: Union[str, Sequence[str], None] = 'b568b2ebfe8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('kb_docs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=256), nullable=False),
    sa.Column('filename', sa.String(length=256), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('received_bytes', sa.BigInteger(), server_default='0', nullable=False),
    sa.Column('sha256', sa.String(length=64), server_default='', nullable=False),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('process_status', sa.String(length=16), nullable=False),
    sa.Column('n_pages', sa.Integer(), server_default='0', nullable=False),
    sa.Column('n_chunks', sa.Integer(), server_default='0', nullable=False),
    sa.Column('n_embedded', sa.Integer(), server_default='0', nullable=False),
    sa.Column('embed_model', sa.String(length=64), server_default='', nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('uploaded_by', sa.String(length=64), nullable=False),
    sa.Column('created_at', app.models.CSTDateTime(), nullable=False),
    sa.Column('processed_at', app.models.CSTDateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_table('kb_pages',
    sa.Column('doc_id', sa.Integer(), nullable=False),
    sa.Column('page_no', sa.Integer(), nullable=False),
    sa.Column('n_chars', sa.Integer(), nullable=False),
    sa.Column('n_images', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['doc_id'], ['kb_docs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('doc_id', 'page_no'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    op.create_table('kb_chunks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('doc_id', sa.Integer(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('page_no', sa.Integer(), nullable=False),
    sa.Column('half', sa.String(length=1), nullable=False),
    sa.Column('text', sa.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql'), nullable=False),
    sa.Column('tokens', sa.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql'), nullable=False),
    sa.Column('embedding', sa.LargeBinary().with_variant(mysql.MEDIUMBLOB(), 'mysql'), nullable=False),
    sa.Column('dim', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['doc_id'], ['kb_docs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_charset='utf8mb4',
    mysql_collate='utf8mb4_unicode_ci'
    )
    with op.batch_alter_table('kb_chunks', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_kb_chunks_doc_id'), ['doc_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 不单独 drop_index：MySQL 里该索引被外键依赖，先删会报 1553；drop_table 会连索引一起删
    op.drop_table('kb_chunks')
    op.drop_table('kb_pages')
    op.drop_table('kb_docs')
