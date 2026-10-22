"""定时采集 worker：每天 06:00（北京时间）跑 daily_collect，每 60 秒处理一次页面上的"补跑"请求。

两类任务放在同一个单线程执行器里串行执行，定时采集和手动补跑不会同时跑同一天（否则会重复调用、主键冲突）。
启动时如果已经过了今天 06:00 且今天还没有 done 的 daily_collect，立即补跑一次（不补数指的是不伪造数据，不是不重跑）。
"""
import logging
import sys
import threading
from datetime import datetime, time

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import timeutil
from app.ark import ArkClient
from app.collector import run_daily, setting
from app.models import JobRun

log = logging.getLogger("geo.worker")
JOB = "daily_collect"
DAILY_AT = time(6, 0)
_lock = threading.Lock()  # 单线程执行器之外再加一道（只在本进程内有效：worker 只能起一个副本）


def _execute(session: Session, jr: JobRun, client: ArkClient, raw_dir) -> JobRun:
    jr.status, jr.started_at = "running", timeutil.now_cst()
    session.commit()
    run_date = jr.run_date  # rollback 后 jr 会过期，日志里不再回库读取（断连时那一读会再抛一次，盖掉原异常）
    try:
        with _lock:
            s = run_daily(session, client, run_date, jr.channel, raw_dir)
    except Exception as e:  # noqa: BLE001  任务失败要落到 JobRun 上，不能让调度器线程悄悄吞掉
        session.rollback()
        log.exception("daily_collect %s 异常", run_date)
        jr.status, jr.message = "failed", f"异常 {type(e).__name__}: {e}"
    else:
        jr.n_ok, jr.n_failed = s.n_ok + s.n_skipped, s.n_failed
        jr.status = "failed" if s.n_failed and not jr.n_ok else "done"
        jr.message = (f"新采 {s.n_ok}，已有 {s.n_skipped}，失败 {s.n_failed}"
                      + (f"：{'、'.join(s.failed_qids)}" if s.failed_qids else ""))
    jr.finished_at = timeutil.now_cst()
    session.commit()
    return jr


def daily_job(session_factory: sessionmaker, client: ArkClient, raw_dir, at: datetime | None = None) -> JobRun:
    with session_factory() as session:
        jr = JobRun(job=JOB, run_date=timeutil.today_cst(at), channel=setting(session, "api_channel", "api-custom"),
                    status="running", n_ok=0, n_failed=0, message="")
        session.add(jr)
        session.commit()
        return _execute(session, jr, client, raw_dir)


def process_requested(session_factory: sessionmaker, client: ArkClient, raw_dir) -> int:
    n = 0
    with session_factory() as session:
        for jr in list(session.scalars(select(JobRun).where(JobRun.job == JOB, JobRun.status == "requested")
                                       .order_by(JobRun.id))):
            _execute(session, jr, client, raw_dir)
            n += 1
    return n


def recover_stale(session_factory: sessionmaker) -> int:
    """启动时收回上次进程留下的 running：worker 是单实例，启动时不可能有别人在跑。
    手动补跑请求改回 requested 重新执行，定时任务记 failed（当天的补跑由 needs_catchup 负责）。"""
    with session_factory() as session:
        stale = list(session.scalars(select(JobRun).where(JobRun.status == "running")))
        for jr in stale:
            if jr.requested_by:
                jr.status = "requested"
            else:
                jr.status, jr.finished_at = "failed", timeutil.now_cst()
                jr.message = (jr.message + "；" if jr.message else "") + "worker 重启，任务中断"
        session.commit()
    return len(stale)


def needs_catchup(session_factory: sessionmaker, at: datetime | None = None) -> bool:
    now = (at or timeutil.now_cst()).astimezone(timeutil.CST)
    if now.time() < DAILY_AT:
        return False
    with session_factory() as session:
        done = session.scalars(select(JobRun.id).where(JobRun.job == JOB, JobRun.run_date == now.date(),
                                                       JobRun.status == "done")).first()
    return done is None


def build_scheduler(session_factory: sessionmaker, client: ArkClient, raw_dir) -> BlockingScheduler:
    sched = BlockingScheduler(timezone="Asia/Shanghai", executors={"default": ThreadPoolExecutor(1)},
                              job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600})
    sched.add_job(daily_job, "cron", hour=DAILY_AT.hour, minute=DAILY_AT.minute, id=JOB,
                  args=[session_factory, client, raw_dir])
    sched.add_job(process_requested, "interval", seconds=60, id="process_requested",
                  args=[session_factory, client, raw_dir])
    return sched


def main() -> None:
    from app.ark import HttpArkClient
    from app.config import get_settings
    from app.db import make_engine
    from app.seed import seed_all

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    cfg = get_settings()
    if not cfg.ark_api_key:
        sys.exit("缺少环境变量 ARK_API_KEY")
    session_factory = sessionmaker(make_engine(cfg.database_url), expire_on_commit=False)
    with session_factory() as s:
        seed_all(s)
    if n := recover_stale(session_factory):
        log.warning("收回 %d 条上次中断的任务", n)
    client = HttpArkClient(cfg.ark_api_key)
    sched = build_scheduler(session_factory, client, cfg.raw_dir)
    if needs_catchup(session_factory):
        log.info("已过 06:00 且今天还没有成功的采集，立即补跑")
        sched.add_job(daily_job, id="catchup", args=[session_factory, client, cfg.raw_dir])
    sched.start()


if __name__ == "__main__":
    main()
