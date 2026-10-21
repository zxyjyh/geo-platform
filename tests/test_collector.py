import json
from datetime import date, datetime, timezone

import pytest

from app import timeutil
from app.collector import run_daily
from app.models import Coding, Run, Source
from app.seed import seed_all
from app.timeutil import today_cst
from tests.fakes import FakeClient

D = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def seeded(session):
    seed_all(session)


@pytest.fixture
def freeze_utc_2026_10_21_2200(monkeypatch):
    fixed = datetime(2026, 10, 21, 22, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(timeutil, "now_cst", lambda: fixed.astimezone(timeutil.CST))


def test_run_daily_writes_runs_sources_codings(session, tmp_path):
    s = run_daily(session, FakeClient.from_trial("custom"), date(2026, 10, 22), "api-custom", tmp_path, sleep_s=0)
    assert (s.n_ok, s.n_failed) == (15, 0)
    r = session.get(Run, "daily-doubao-api-custom-Q01-20261022")
    assert r.collect_date == date(2026, 10, 22) and r.round == "daily" and r.question_version == "v3"
    assert session.query(Source).count() == 69
    assert session.query(Coding).filter_by(alias_version=1).count() == 15


def test_raw_file_has_trial_format(session, tmp_path):
    run_daily(session, FakeClient.from_trial("custom"), D, "api-custom", tmp_path, sleep_s=0)
    r = session.get(Run, "daily-doubao-api-custom-Q01-20261022")
    saved = json.loads((tmp_path / "daily-doubao-api-custom-Q01-20261022.json").read_text(encoding="utf-8"))
    assert set(saved) == {"request", "response", "collected_at"}
    assert saved["request"]["tools"] == [{"type": "web_search", "sources": ["doubao"]}]
    assert r.raw_path.endswith("daily-doubao-api-custom-Q01-20261022.json")
    assert r.billed_searches == 3 and r.search_rounds == 3 and " | " in r.search_queries


def test_failure_after_retries_records_failed_no_fabrication(session, tmp_path):
    c = FakeClient.failing_for({"Q05"}, times=3)
    s = run_daily(session, c, date(2026, 10, 22), "api-custom", tmp_path, sleep_s=0)
    r = session.get(Run, "daily-doubao-api-custom-Q05-20261022")
    assert r.status == "failed" and r.error and r.answer_text == ""
    assert s.failed_qids == ["Q05"] and c.calls_for("Q05") == 3
    assert session.query(Coding).filter_by(run_id=r.run_id).count() == 0
    assert session.query(Source).filter_by(run_id=r.run_id).count() == 0


def test_success_on_last_retry_is_valid(session, tmp_path):
    c = FakeClient.failing_for({"Q05"}, times=2)
    s = run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0)
    assert s.n_failed == 0 and session.get(Run, "daily-doubao-api-custom-Q05-20261022").status == "valid"


def test_rerun_same_day_only_retries_failed(session, tmp_path):
    run_daily(session, FakeClient.failing_for({"Q05"}, times=3), D, "api-custom", tmp_path, sleep_s=0)
    c2 = FakeClient.from_trial("custom")
    s2 = run_daily(session, c2, D, "api-custom", tmp_path, sleep_s=0)
    assert c2.total_calls == 1 and s2.n_skipped == 14
    assert session.query(Run).filter_by(collect_date=D).count() == 15
    assert session.get(Run, "daily-doubao-api-custom-Q05-20261022").status == "valid"
    assert session.query(Source).count() == 69


def test_empty_answer_is_void(session, tmp_path):
    c = FakeClient.from_trial("custom", overrides={"Q01": {"output": [], "usage": {}}})
    run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0)
    r = session.get(Run, "daily-doubao-api-custom-Q01-20261022")
    assert r.status == "void" and session.query(Coding).filter_by(run_id=r.run_id).count() == 0


def test_collect_date_is_cst(session, tmp_path, freeze_utc_2026_10_21_2200):
    run_daily(session, FakeClient.from_trial("custom"), today_cst(), "api-custom", tmp_path, sleep_s=0)
    r = session.get(Run, "daily-doubao-api-custom-Q01-20261022")
    assert r is not None and r.collect_date == date(2026, 10, 22)
    assert r.collected_at.isoformat() == "2026-10-22T06:00:00+08:00"
