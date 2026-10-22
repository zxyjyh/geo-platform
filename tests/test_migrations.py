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
            "source_tags", "job_runs", "users", "settings", "brand_marks"} <= tables
    assert "rep" in {c["name"] for c in inspect(create_engine(url)).get_columns("runs")}
    assert {"review_strictness", "allows_links", "notes"} <= {c["name"] for c in inspect(create_engine(url)).get_columns("platforms")}


def test_mysql_ddl_case_sensitive_columns_use_bin_collation(capsys):
    # utf8mb4_unicode_ci 不区分大小写：Aomi/aomi/AOMI 会撞 aliases 的唯一约束，URL 路径大小写不同也会被当成同一篇
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = "mysql+pymysql://u:p@localhost/geo"
    command.upgrade(cfg, "head", sql=True)
    ddl = capsys.readouterr().out
    assert "alias VARCHAR(64) COLLATE utf8mb4_bin" in ddl
    assert ddl.count("url_norm VARCHAR(768) COLLATE utf8mb4_bin") == 2
