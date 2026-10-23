from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis import growth_index
from app.api.common import ModelPlatform, alias_version, api_channel, date_range, first_date, latest_date, to_json
from app.attribution import attribution_daily
from app.auth import current_user
from app.collector import ROUND, setting
from app.db import get_session
from app.metrics import daily_metrics, trend, unbranded_qids
from app.models import JobRun, Question, Run
from app.timeutil import today_cst

router = APIRouter(prefix="/dashboard", dependencies=[Depends(current_user)])


def _price(session: Session, key: str) -> float | None:
    v = setting(session, key, "")
    try:
        return float(v) if v != "" else None
    except ValueError:
        return None


@router.get("")
def dashboard(date: date | None = None, channel: str | None = None, platform: ModelPlatform = "doubao",
              session: Session = Depends(get_session)):
    channel = api_channel(session, channel)
    latest = latest_date(session, channel, platform)
    d = date or latest or today_cst()
    v = alias_version(session)
    m = daily_metrics(session, d, channel, v, platform=platform)
    # 按场景分组（参考 Answerbit 的"分组"和诊断报告的场景划分）：口径和总指标相同，只是题目范围按场景切开
    qids = unbranded_qids(session)
    scenes: dict[str, list[str]] = {}
    for q in session.scalars(select(Question).where(Question.version == setting(session, "question_version", "v3"),
                                                    Question.qid.in_(qids)).order_by(Question.qid)):
        scenes.setdefault(q.scene, []).append(q.qid)
    jr = session.scalars(select(JobRun).where(JobRun.job == "daily_collect", JobRun.run_date == d,
                                              JobRun.channel == channel).order_by(JobRun.id.desc())).first()
    billed, tin, tout = session.execute(
        select(func.sum(Run.billed_searches), func.sum(Run.input_tokens), func.sum(Run.output_tokens))
        .where(Run.round == ROUND, Run.platform == platform, Run.channel == channel, Run.collect_date == d)).one()
    billed, tin, tout = billed or 0, tin or 0, tout or 0
    prices = [_price(session, k) for k in ("price_per_search_yuan", "price_input_per_1k_yuan",
                                           "price_output_per_1k_yuan")]
    # 三项单价都配置了才估算，缺一项就显示"未配置单价"，不拿 0 顶替
    cost = None if None in prices else billed * prices[0] + tin / 1000 * prices[1] + tout / 1000 * prices[2]
    # 增长指数：最近 7 天各项指标的线性回归斜率
    growth_start = d - timedelta(days=6)
    recent = trend(session, growth_start, d, channel, v, platform)
    def _ratio_series(metric_key: str) -> list[float]:
        out: list[float] = []
        for dm in recent:
            r = getattr(dm, metric_key)["aomi"]
            out.append(r.num / r.den if r.den > 0 else 0.0)
        return out
    growth = {
        "mention": growth_index(_ratio_series("mention")),
        "first": growth_index(_ratio_series("first")),
        "share": growth_index(_ratio_series("share")),
    }
    return {
        "date": d, "platform": platform, "channel": channel, "latest_date": latest,
        "first_date": first_date(session, channel, platform),
        "today": today_cst(), "metrics": to_json(m),
        "by_scene": [{"scene": sc, "qids": qs, "metrics": to_json(daily_metrics(session, d, channel, v, qs, platform))}
                     for sc, qs in scenes.items()],
        "job": None if jr is None else {"status": jr.status, "n_ok": jr.n_ok, "n_failed": jr.n_failed,
                                        "message": jr.message},
        "usage": {"billed_searches": billed, "input_tokens": tin, "output_tokens": tout, "est_cost_yuan": cost},
        "growth": growth,
    }


@router.get("/trend")
def dashboard_trend(start: date | None = None, end: date | None = None, channel: str | None = None,
                    platform: ModelPlatform = "doubao", session: Session = Depends(get_session)):
    channel = api_channel(session, channel)
    start, end = date_range(start, end or latest_date(session, channel, platform))
    return [to_json(m) for m in trend(session, start, end, channel, alias_version(session), platform)]


@router.get("/attribution")
def dashboard_attribution(date: date | None = None, channel: str | None = None, platform: ModelPlatform = "doubao",
                          session: Session = Depends(get_session)):
    channel = api_channel(session, channel)
    d = date or latest_date(session, channel, platform) or today_cst()
    return to_json(attribution_daily(session, d, channel, alias_version(session), platform))


@router.get("/positioning")
def positioning(date: date | None = None, channel: str | None = None, platform: ModelPlatform = "doubao",
                session: Session = Depends(get_session)):
    """竞品横向占位表：每道题每个品牌的名次。

    返回：
    {
        "date": "2026-10-23",
        "channel": "api-custom",
        "questions": [
            {"qid": "Q01", "text": "澳门外卖平台推荐", "scene": "外卖"},
            ...
        ],
        "brands": ["aomi", "mfood", "shanfeng"],
        "matrix": {
            "Q01": {"aomi": 1, "mfood": 2, "shanfeng": null},
            "Q02": {"aomi": null, "mfood": 1, "shanfeng": 3},
            ...
        }
    }

    null 表示该题没提到该品牌。
    """
    from app.models import Coding

    channel = api_channel(session, channel)
    latest = latest_date(session, channel, platform)
    d = date or latest or today_cst()
    v = alias_version(session)
    q_version = setting(session, "question_version", "v3")

    # Get all questions for this version
    questions = list(session.scalars(
        select(Question).where(Question.version == q_version).order_by(Question.qid)
    ))

    # Get codings for this date: join runs with codings
    rows = list(session.execute(
        select(Run.qid, Coding)
        .join(Coding, (Coding.run_id == Run.run_id) & (Coding.alias_version == v))
        .where(Run.round == ROUND, Run.platform == platform, Run.channel == channel,
               Run.collect_date == d, Run.status == "valid")
    ))

    # Build matrix: for each qid, get the order for each entity
    # If multiple runs per qid, take the first one encountered
    matrix: dict[str, dict[str, int | None]] = {}
    for qid, coding in rows:
        if qid not in matrix:
            matrix[qid] = {
                "aomi": coding.order_aomi,
                "mfood": coding.order_mfood,
                "shanfeng": coding.order_shanfeng
            }

    return {
        "date": d,
        "channel": channel,
        "questions": [
            {"qid": q.qid, "text": q.text, "scene": q.scene}
            for q in questions
        ],
        "brands": ["aomi", "mfood", "shanfeng"],
        "matrix": matrix
    }
