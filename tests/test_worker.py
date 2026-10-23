from datetime import date, datetime, timezone

import pytest

from app.models import JobRun, Run
from app.seed import seed_all
from app.timeutil import CST
from app.worker import build_scheduler, daily_job, needs_catchup, process_requested
from tests.fakes import FakeClient

QIDS = [f"Q{i:02d}" for i in range(1, 16)]


@pytest.fixture(autouse=True)
def seeded(session, monkeypatch):
    seed_all(session)
    monkeypatch.setattr("app.collector.time.sleep", lambda s: None)   # worker 走 run_daily 的默认间隔


def test_daily_job_uses_cst_date(session_factory, tmp_path):
    jr = daily_job(session_factory, FakeClient.from_trial("custom"), tmp_path, at=datetime(2026,10,21,22,0,tzinfo=timezone.utc))
    assert jr.run_date == date(2026, 10, 22) and jr.status == "done" and jr.n_ok == 15
    assert jr.started_at is not None and jr.finished_at is not None


def test_process_requested_runs_and_marks_done(session_factory, session, tmp_path):
    session.add(JobRun(job="daily_collect", run_date=date(2026, 10, 20), channel="api-custom", status="requested",
                       requested_by="alice", n_ok=0, n_failed=0, message=""))
    session.commit()
    assert process_requested(session_factory, FakeClient.from_trial("custom"), tmp_path) == 1
    session.expire_all()
    jr = session.query(JobRun).one()
    assert jr.status == "done" and jr.n_ok == 15
    assert session.get(Run, "daily-doubao-api-custom-Q01-20261020") is not None
    assert process_requested(session_factory, FakeClient.from_trial("custom"), tmp_path) == 0


def test_job_failed_status_when_all_fail(session_factory, tmp_path):   # 15 题全部失败 → status == "failed"，message 里列出全部题号
    jr = daily_job(session_factory, FakeClient.failing_for(set(QIDS), times=3), tmp_path,
                   at=datetime(2026, 10, 22, 6, 0, tzinfo=CST))
    assert jr.status == "failed" and all(q in jr.message for q in QIDS)


def test_partial_failure_is_done_with_failed_qids(session_factory, tmp_path):
    jr = daily_job(session_factory, FakeClient.failing_for({"Q05"}, times=3), tmp_path,
                   at=datetime(2026, 10, 22, 6, 0, tzinfo=CST))
    assert (jr.status, jr.n_ok, jr.n_failed) == ("done", 14, 1) and "Q05" in jr.message


def test_unexpected_exception_marks_job_failed(session_factory, tmp_path):
    class Boom:
        def create(self, body):
            raise RuntimeError("db down?")

    jr = daily_job(session_factory, Boom(), tmp_path, at=datetime(2026, 10, 22, 6, 0, tzinfo=CST))
    assert jr.status == "failed" and "RuntimeError" in jr.message and jr.finished_at is not None


def test_needs_catchup(session_factory, session, tmp_path):
    before_10 = datetime(2026, 10, 22, 9, 59, tzinfo=CST)
    after_10 = datetime(2026, 10, 22, 2, 30, tzinfo=timezone.utc)      # 北京时间 10-22 10:30
    assert not needs_catchup(session_factory, before_10)
    assert needs_catchup(session_factory, after_10)
    daily_job(session_factory, FakeClient.from_trial("custom"), tmp_path, at=after_10)
    assert not needs_catchup(session_factory, after_10)


def test_scheduler_is_serial_and_scheduled_at_10_cst(session_factory, tmp_path):
    # 定时采集和手动补跑必须串行（Task 4 的并发问题由这里保证）
    sched = build_scheduler(session_factory, FakeClient.from_trial("custom"), tmp_path)
    assert sched._executors["default"]._pool._max_workers == 1
    jobs = {j.id: j for j in sched.get_jobs()}
    daily = jobs["daily_collect"]
    assert str(daily.trigger.timezone) == "Asia/Shanghai" and "hour='10'" in str(daily.trigger)
    assert sched._job_defaults == {"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
    assert "process_requested" in jobs


def test_recover_stale_running_jobs_on_startup(session_factory, session):
    from app.worker import recover_stale

    session.add_all([
        JobRun(job="daily_collect", run_date=date(2026, 10, 22), channel="api-custom", status="running",
               requested_by="alice", n_ok=0, n_failed=0, message=""),
        JobRun(job="daily_collect", run_date=date(2026, 10, 22), channel="api-custom", status="running",
               requested_by=None, n_ok=0, n_failed=0, message=""),
    ])
    session.commit()
    assert recover_stale(session_factory) == 2
    session.expire_all()
    manual, scheduled = session.query(JobRun).order_by(JobRun.id).all()
    assert manual.status == "requested"                       # 手动补跑请求重新排队，不静默丢失
    assert scheduled.status == "failed" and "重启" in scheduled.message


def test_scheduler_adds_kb_job_only_with_embedder_and_kb_dir(session_factory, tmp_path):
    from tests.fakes import FakeEmbedder

    client = FakeClient.from_trial("custom")
    with_kb = build_scheduler(session_factory, client, tmp_path, FakeEmbedder(), tmp_path)
    assert "kb_process" in {j.id for j in with_kb.get_jobs()}
    without = build_scheduler(session_factory, client, tmp_path)
    assert "kb_process" not in {j.id for j in without.get_jobs()}
