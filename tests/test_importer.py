from datetime import date

import pytest

from app.importer import import_trial
from app.models import Coding, Run, Source
from app.seed import seed_all


@pytest.fixture(autouse=True)
def seeded(session):
    seed_all(session)


def test_import_trial(session):
    assert import_trial(session) == 30 and import_trial(session) == 0
    assert session.query(Run).filter_by(round="trial").count() == 30
    assert session.query(Source).count() == 165
    assert {r.question_version for r in session.query(Run)} == {"v3"}


def test_import_trial_fields(session):
    import_trial(session)
    r = session.get(Run, "trial-doubao-api-plugin-Q01-1")
    assert (r.channel, r.qid, r.round, r.status) == ("api-plugin", "Q01", "trial", "valid")
    assert r.collect_date == date(2026, 10, 21) and r.collected_at.utcoffset().total_seconds() == 8 * 3600
    assert r.raw_path == "data/raw/trial/trial-doubao-api-plugin-Q01-1.json"
    assert session.query(Coding).count() == 30


def test_cli_import_trial_on_fresh_db(tmp_path, monkeypatch, capsys):
    from alembic import command
    from alembic.config import Config

    from app import cli
    from app.config import ROOT

    url = f"sqlite:///{tmp_path / 'cli.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    monkeypatch.setenv("DATABASE_URL", url)
    cli.main(["import-trial"])
    assert "导入 30" in capsys.readouterr().out
