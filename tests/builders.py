"""构造 Run / Coding 测试数据。"""
from datetime import date, datetime, time

from app.collector import daily_run_id, new_run
from app.models import Coding
from app.timeutil import CST

UNBRANDED = ["Q01", "Q02", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10", "Q11"]


def add_run(session, qid: str, d: date, channel: str = "api-custom", status: str = "valid",
            mention: dict | None = None, order: dict | None = None, alias_version: int = 1,
            round_: str = "daily", text: str = "回答", run_id: str | None = None,
            collected_at: datetime | None = None):
    if run_id is None:
        run_id = daily_run_id(channel, qid, d) if round_ == "daily" else f"{round_}-{channel}-{qid}-{d}"
    run = new_run(run_id, qid, "v3", channel, d, collected_at or datetime.combine(d, time(6), tzinfo=CST),
                  round_=round_)
    run.status = status
    run.answer_text = text if status == "valid" else ""
    session.add(run)
    if status == "valid":
        m = {"aomi": False, "mfood": False, "shanfeng": False, **(mention or {})}
        o = {"aomi": None, "mfood": None, "shanfeng": None, **(order or {})}
        session.add(Coding(run_id=run.run_id, alias_version=alias_version,
                           mention_aomi=m["aomi"], mention_mfood=m["mfood"], mention_shanfeng=m["shanfeng"],
                           order_aomi=o["aomi"], order_mfood=o["mfood"], order_shanfeng=o["shanfeng"]))
    session.commit()
    return run


def add_source(session, run, url: str, title: str = "t", rank: int = 1, is_owned: bool = False):
    from urllib.parse import urlparse

    from sqlalchemy import select

    from app.models import Platform, Source
    from app.urls import normalize_url, platform_for

    domain = urlparse(url).netloc
    s = Source(run_id=run.run_id, rank=rank, title=title, url=url, url_norm=normalize_url(url), domain=domain,
               platform_key=platform_for(domain, list(session.scalars(select(Platform)))), is_owned=is_owned)
    session.add(s)
    session.commit()
    return s
