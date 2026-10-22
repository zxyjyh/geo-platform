"""MySQL 冒烟测试：只在设置了 MYSQL_TEST_URL 时运行（uv run pytest -m mysql）。
例：MYSQL_TEST_URL='mysql+pymysql://root:pw@127.0.0.1:3307/geo_test?charset=utf8mb4'"""
import json
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker

from app.config import ROOT
from app.db import make_engine
from app.importer import TRIAL_DIR, import_trial
from app.models import Alias, Run, Source, SourceTag
from app.seed import seed_all

URL = os.environ.get("MYSQL_TEST_URL")
pytestmark = [pytest.mark.mysql, pytest.mark.skipif(not URL, reason="需要 MYSQL_TEST_URL")]


@pytest.fixture(scope="module")
def mysql_session():
    engine = make_engine(URL)
    with engine.begin() as c:                      # 每次从空库开始
        c.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for (t,) in c.execute(text("SHOW TABLES")).all():
            c.execute(text(f"DROP TABLE `{t}`"))
        c.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = URL
    command.upgrade(cfg, "head")
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    engine.dispose()


def test_seed_and_import_trial_on_mysql(mysql_session):
    s = mysql_session
    seed_all(s)
    seed_all(s)
    assert import_trial(s) == 30
    assert s.query(Run).count() == 30 and s.query(Source).count() == 165


def test_case_sensitive_aliases_coexist(mysql_session):
    # Task 1 审核发现：utf8mb4_unicode_ci 下 Aomi/aomi/AOMI 会撞唯一约束
    got = set(mysql_session.scalars(select(Alias.alias).where(Alias.version == 1, Alias.entity == "aomi")))
    assert {"Aomi", "aomi", "AOMI"} <= got


def test_url_norm_is_case_sensitive(mysql_session):
    mysql_session.add_all([SourceTag(url_norm="https://x.com/A", tag="external_geo", note=""),
                           SourceTag(url_norm="https://x.com/a", tag="external_geo", note="")])
    mysql_session.commit()
    assert mysql_session.get(SourceTag, "https://x.com/A").url_norm == "https://x.com/A"


def test_chinese_answer_text_roundtrip(mysql_session):
    path = TRIAL_DIR / "trial-doubao-api-custom-Q01-1.json"
    from app.ark import parse
    original = parse(json.loads(path.read_text(encoding="utf-8"))["response"]).text
    mysql_session.expire_all()
    assert mysql_session.get(Run, "trial-doubao-api-custom-Q01-1").answer_text == original
    assert "澳" in original
