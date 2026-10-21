"""每日采集：v3 的题逐题调用方舟，原始响应落盘，run / sources / codings 入库。

失败重试 retries 次，仍失败就写 status=failed 的 run，绝不补数。
同一天重复执行时，已经 valid / void 的题跳过，failed 的题删掉重跑。每题单独提交。
"""
import json
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import timeutil
from app.ark import DEFAULT_MODEL, ArkClient, ArkError, ArkResult, build_body, parse, parse_publish_time
from app.coding import code_answer, load_aliases
from app.models import Coding, OwnedPrefix, Platform, Question, Run, Setting, Source
from app.urls import is_owned, normalize_url, platform_for

ROUND = "daily"


@dataclass
class JobSummary:
    run_date: date
    channel: str
    n_ok: int = 0
    n_failed: int = 0
    n_skipped: int = 0
    failed_qids: list[str] = field(default_factory=list)


def setting(session: Session, key: str, default: str = "") -> str:
    row = session.get(Setting, key)
    return row.value if row is not None and row.value != "" else default


def daily_run_id(channel: str, qid: str, d: date) -> str:
    return f"daily-doubao-{channel}-{qid}-{d:%Y%m%d}"


def store_run(session: Session, run: Run, result: ArkResult) -> None:
    """把解析结果写进 run，并写 Source 行和当前 alias_version 的 Coding。collector 和 importer 共用。不提交。"""
    run.answer_text = result.text
    run.status = "valid" if result.text else "void"
    run.sources_count = len(result.citations)
    run.sources_visible = bool(result.citations)
    run.search_queries = " | ".join(result.search_queries)
    run.search_rounds = len(result.search_queries)
    run.billed_searches = result.billed_searches
    run.input_tokens = result.input_tokens
    run.output_tokens = result.output_tokens
    session.add(run)

    platforms = list(session.scalars(select(Platform)))
    prefixes = list(session.scalars(select(OwnedPrefix)))
    for k, c in enumerate(result.citations):
        url = c.get("url", "")
        domain = urlparse(url).netloc
        raw_time = c.get("publish_time") or ""
        session.add(Source(run_id=run.run_id, rank=k + 1, title=c.get("title", ""), url=url,
                           url_norm=normalize_url(url), domain=domain, site_name=c.get("site_name", ""),
                           publish_time_raw=str(raw_time), publish_time=parse_publish_time(str(raw_time)),
                           platform_key=platform_for(domain, platforms), is_owned=is_owned(url, prefixes)))

    if run.status == "valid":
        version = int(setting(session, "alias_version", "1"))
        r = code_answer(result.text, load_aliases(session, version))
        session.add(Coding(run_id=run.run_id, alias_version=version,
                           mention_aomi=r.mention["aomi"], mention_mfood=r.mention["mfood"],
                           mention_shanfeng=r.mention["shanfeng"], order_aomi=r.order["aomi"],
                           order_mfood=r.order["mfood"], order_shanfeng=r.order["shanfeng"]))


def new_run(run_id: str, qid: str, question_version: str, channel: str, run_date: date, collected_at,
            round_: str = ROUND, collector: str = "app.collector") -> Run:
    return Run(run_id=run_id, round=round_, qid=qid, question_version=question_version, platform="doubao",
               channel=channel, channel_detail=f"{DEFAULT_MODEL} / web_search {channel}", mode="联网",
               collected_at=collected_at, collect_date=run_date, collector=collector,
               account_ref="ark-default", location="中国/广东/深圳" if channel == "api-plugin" else "未设置",
               new_session=True, answer_text="", raw_path="", sources_visible=False, sources_count=0,
               search_queries="", search_rounds=0)


def _delete_run(session: Session, run: Run) -> None:
    session.query(Source).filter_by(run_id=run.run_id).delete()
    session.query(Coding).filter_by(run_id=run.run_id).delete()
    session.delete(run)
    session.flush()


def run_daily(session: Session, client: ArkClient, run_date: date, channel: str, raw_dir: Path,
              sleep_s: float = 1.0, retries: int = 2) -> JobSummary:
    version = setting(session, "question_version", "v3")
    questions = list(session.scalars(select(Question).where(Question.version == version).order_by(Question.qid)))
    summary = JobSummary(run_date=run_date, channel=channel)
    raw_dir.mkdir(parents=True, exist_ok=True)
    called = False

    for q in questions:
        run_id = daily_run_id(channel, q.qid, run_date)
        existing = session.get(Run, run_id)
        if existing is not None and existing.status in ("valid", "void"):
            summary.n_skipped += 1
            continue
        if existing is not None:
            _delete_run(session, existing)

        if called and sleep_s:
            time.sleep(sleep_s)
        called = True
        body = build_body(q.text, channel)
        resp, error = None, None
        for attempt in range(retries + 1):
            if attempt and sleep_s:
                time.sleep(sleep_s)
            try:
                resp = client.create(body)
                break
            except ArkError as e:
                error = f"第 {attempt + 1} 次：{e}"
        collected_at = timeutil.now_cst()

        if resp is not None:
            raw_path = raw_dir / f"{run_id}.json"
            try:
                raw_path.write_text(json.dumps({"request": body, "response": resp,
                                                "collected_at": collected_at.isoformat(timespec="seconds")},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
                run = new_run(run_id, q.qid, q.version, channel, run_date, collected_at)
                run.raw_path = str(raw_path.resolve())
                store_run(session, run, parse(resp))
                session.commit()
                summary.n_ok += 1
                continue
            except Exception as e:  # noqa: BLE001  一题的响应异常 / 字段超长不能打断其余的题
                session.rollback()
                error = f"入库失败 {type(e).__name__}: {e}"

        run = new_run(run_id, q.qid, q.version, channel, run_date, collected_at)
        run.status, run.error = "failed", error
        session.add(run)
        session.commit()
        summary.n_failed += 1
        summary.failed_qids.append(q.qid)
    return summary
