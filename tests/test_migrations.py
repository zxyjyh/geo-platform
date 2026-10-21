from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.config import ROOT


def test_alembic_upgrade_head_creates_all_tables(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    tables = set(inspect(create_engine(url)).get_table_names())
    assert {"questions", "runs", "sources", "codings", "aliases", "platforms", "owned_prefixes",
            "source_tags", "job_runs", "users", "settings"} <= tables
