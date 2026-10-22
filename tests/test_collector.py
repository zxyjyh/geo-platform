import json
from datetime import date, datetime, timezone

import pytest

from app import timeutil
from app.collector import daily_run_id, run_daily
from app.models import Coding, Run, Setting, Source
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


def test_unexpected_error_on_one_question_records_failed_and_continues(session, tmp_path):
    # 响应结构异常（parse 会抛 TypeError）不能打断当天其余的题，也不能不留记录
    c = FakeClient.from_trial("custom", overrides={"Q03": {"output": None}})
    s = run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0)
    r = session.get(Run, "daily-doubao-api-custom-Q03-20261022")
    assert r.status == "failed" and "TypeError" in r.error
    assert (s.n_ok, s.n_failed, s.failed_qids) == (14, 1, ["Q03"])
    assert session.query(Source).filter_by(run_id=r.run_id).count() == 0


def test_run_daily_backfills_runs_missing_current_alias_version(session, tmp_path):
    # 采集中途别名表升了版本：先前用旧版本编码入库的 run，在本次采集结束时补上当前版本的编码
    from app.models import Alias, Setting
    from tests.builders import add_run

    old = add_run(session, "Q01", date(2026, 10, 20), mention={"aomi": True}, order={"aomi": 1}, alias_version=1)
    for a in session.query(Alias).filter_by(version=1).all():
        session.add(Alias(version=2, entity=a.entity, alias=a.alias))
    session.get(Setting, "alias_version").value = "2"
    session.commit()
    run_daily(session, FakeClient.from_trial("custom"), D, "api-custom", tmp_path, sleep_s=0)
    assert session.get(Coding, (old.run_id, 2)) is not None


def test_run_id_rep_suffix():
    d = date(2026, 10, 22)
    assert daily_run_id("api-custom", "Q01", d) == "daily-doubao-api-custom-Q01-20261022"
    assert daily_run_id("api-custom", "Q01", d, 2) == "daily-doubao-api-custom-Q01-20261022-r2"


def test_run_daily_repeats_two(session, tmp_path):
    c = FakeClient.from_trial("custom")
    s = run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0, repeats=2)
    assert (s.n_ok, c.total_calls, c.calls_for("Q01")) == (30, 30, 2)
    r2 = session.get(Run, "daily-doubao-api-custom-Q01-20261022-r2")
    assert r2.rep == 2 and r2.status == "valid"


def test_run_daily_failed_rep_reported_with_suffix(session, tmp_path):
    run_daily(session, FakeClient.from_trial("custom"), D, "api-custom", tmp_path, sleep_s=0, repeats=1)
    c = FakeClient.failing_for(["Q01"], 3)        # 第 1 次已 valid 跳过；第 2 次用完重试仍失败
    s = run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0, repeats=2)
    assert s.failed_qids == ["Q01-r2"] and session.get(Run, "daily-doubao-api-custom-Q01-20261022-r2").status == "failed"


def test_run_daily_reads_setting_and_keeps_existing_r2(session, tmp_path):
    session.get(Setting, "repeats_per_question_api").value = "2"; session.commit()
    run_daily(session, FakeClient.from_trial("custom"), D, "api-custom", tmp_path, sleep_s=0)
    session.get(Setting, "repeats_per_question_api").value = "1"; session.commit()
    c = FakeClient.from_trial("custom")
    run_daily(session, c, D, "api-custom", tmp_path, sleep_s=0)
    assert c.total_calls == 0 and session.query(Run).count() == 30   # 改回 1 不删已采到的 r2
