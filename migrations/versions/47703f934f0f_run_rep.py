"""run rep

Revision ID: 47703f934f0f
Revises: 79106b7850c9
Create Date: 2026-10-22 18:32:16.331966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models


# revision identifiers, used by Alembic.
revision: str = '47703f934f0f'
down_revision: Union[str, Sequence[str], None] = '79106b7850c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("runs", sa.Column("rep", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "rep")
