from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import alias_version, api_channel, date_range, latest_date, to_json
from app.auth import current_user
from app.collector import ROUND, setting
from app.db import get_session
from app.metrics import daily_metrics, trend
from app.models import JobRun, Run
from app.timeutil import today_cst

router = APIRouter(prefix="/dashboard", dependencies=[Depends(current_user)])


def _price(session: Session, key: str) -> float | None:
    v = setting(session, key, "")
    try:
        return float(v) if v != "" else None
    except ValueError:
        return None


@router.get("")
def dashboard(date: date | None = None, channel: str | None = None, session: Session = Depends(get_session)):
    channel = api_channel(session, channel)
    latest = latest_date(session, channel)
    d = date or latest or today_cst()
    m = daily_metrics(session, d, channel, alias_version(session))
    jr = session.scalars(select(JobRun).where(JobRun.job == "daily_collect", JobRun.run_date == d,
                                              JobRun.channel == channel).order_by(JobRun.id.desc())).first()
    billed, tin, tout = session.execute(
        select(func.sum(Run.billed_searches), func.sum(Run.input_tokens), func.sum(Run.output_tokens))
        .where(Run.round == ROUND, Run.channel == channel, Run.collect_date == d)).one()
    billed, tin, tout = billed or 0, tin or 0, tout or 0
    prices = [_price(session, k) for k in ("price_per_search_yuan", "price_input_per_1k_yuan",
                                           "price_output_per_1k_yuan")]
    # 三项单价都配置了才估算，缺一项就显示"未配置单价"，不拿 0 顶替
    cost = None if None in prices else billed * prices[0] + tin / 1000 * prices[1] + tout / 1000 * prices[2]
    return {
        "date": d, "channel": channel, "latest_date": latest, "metrics": to_json(m),
        "job": None if jr is None else {"status": jr.status, "n_ok": jr.n_ok, "n_failed": jr.n_failed,
                                        "message": jr.message},
        "usage": {"billed_searches": billed, "input_tokens": tin, "output_tokens": tout, "est_cost_yuan": cost},
    }


@router.get("/trend")
def dashboard_trend(start: date | None = None, end: date | None = None, channel: str | None = None,
                    session: Session = Depends(get_session)):
    channel = api_channel(session, channel)
    start, end = date_range(start, end or latest_date(session, channel))
    return [to_json(m) for m in trend(session, start, end, channel, alias_version(session))]
