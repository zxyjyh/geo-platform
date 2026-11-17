"""prune platforms to the seeded three

种子平台 7→3（什么值得买/头条号/搜狐）：删掉百家号/B站/网易号/知乎。
依据：3 天监测里这 4 个平台被引 0 次（信源表无一行），且不在发布计划内。
这些行无属性/备注数据，删除不丢信息；downgrade 按旧种子原样恢复。

Revision ID: 8eec3cb123fc
Revises: a1b2c3d4e5f6
Create Date: 2026-11-17 12:03:06.782922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models


# revision identifiers, used by Alembic.
revision: str = '8eec3cb123fc'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REMOVED = ["baijiahao", "bilibili", "netease", "zhihu"]
# 旧种子（HEAD~ 的 app/seed.py）里的原值，供 downgrade 恢复
OLD_ROWS = [
    ("baijiahao", "百家号", "baijiahao.baidu.com"),
    ("bilibili", "B站", "bilibili.com"),
    ("netease", "网易号", "163.com"),
    ("zhihu", "知乎", "zhihu.com"),
]


def upgrade() -> None:
    """Upgrade schema."""
    platforms = sa.table("platforms", sa.column("key", sa.String))
    op.execute(platforms.delete().where(platforms.c.key.in_(REMOVED)))


def downgrade() -> None:
    """Downgrade schema."""
    op.bulk_insert(
        sa.table("platforms",
                 sa.column("key", sa.String),
                 sa.column("name", sa.String),
                 sa.column("domain_suffix", sa.String),
                 sa.column("publishable", sa.Boolean),
                 sa.column("review_strictness", sa.String),
                 sa.column("allows_links", sa.String),
                 sa.column("notes", sa.String)),
        [dict(key=k, name=n, domain_suffix=s, publishable=True,
              review_strictness="unknown", allows_links="unknown", notes="")
         for k, n, s in OLD_ROWS],
    )
