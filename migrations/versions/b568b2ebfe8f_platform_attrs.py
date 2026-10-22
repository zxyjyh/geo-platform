"""platform attrs

Revision ID: b568b2ebfe8f
Revises: 326cd29287b6
Create Date: 2026-10-22 18:42:46.265217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models


# revision identifiers, used by Alembic.
revision: str = 'b568b2ebfe8f'
down_revision: Union[str, Sequence[str], None] = '326cd29287b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("platforms", schema=None) as batch_op:
        batch_op.add_column(sa.Column("review_strictness", sa.String(length=16), nullable=False, server_default="unknown"))
        batch_op.add_column(sa.Column("allows_links", sa.String(length=16), nullable=False, server_default="unknown"))
        batch_op.add_column(sa.Column("notes", sa.String(length=500), nullable=False, server_default=""))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("platforms", schema=None) as batch_op:
        batch_op.drop_column("notes")
        batch_op.drop_column("allows_links")
        batch_op.drop_column("review_strictness")
