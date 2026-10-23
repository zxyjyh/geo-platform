"""构造 Run / Coding 测试数据。"""
from datetime import date, datetime, time
from pathlib import Path

import pymupdf

from app.collector import daily_run_id, new_run
from app.models import Coding
from app.timeutil import CST

UNBRANDED = ["Q01", "Q02", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10", "Q11"]


def add_run(session, qid: str, d: date, channel: str = "api-custom", status: str = "valid",
            mention: dict | None = None, order: dict | None = None, alias_version: int = 1,
            round_: str = "daily", text: str = "回答", run_id: str | None = None,
            collected_at: datetime | None = None, rep: int = 1):
    if run_id is None:
        run_id = daily_run_id(channel, qid, d, rep) if round_ == "daily" else f"{round_}-{channel}-{qid}-{d}"
    run = new_run(run_id, qid, "v3", channel, d, collected_at or datetime.combine(d, time(6), tzinfo=CST),
                  round_=round_, rep=rep)
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


def add_source(session, run, url: str, title: str = "t", rank: int = 1, is_owned: bool = False,
               publish_time: datetime | None = None):
    from urllib.parse import urlparse

    from sqlalchemy import select

    from app.models import Platform, Source
    from app.urls import normalize_url, platform_for

    domain = urlparse(url).netloc
    s = Source(run_id=run.run_id, rank=rank, title=title, url=url, url_norm=normalize_url(url), domain=domain,
               platform_key=platform_for(domain, list(session.scalars(select(Platform)))), is_owned=is_owned,
               publish_time=publish_time)
    session.add(s)
    session.commit()
    return s


def _build_pdf(pages: list[str | None], landscape: bool = False) -> pymupdf.Document:
    """每个字符串一页；None 表示只画一个矩形、没有文字层。"""
    w, h = (842, 595) if landscape else (595, 842)
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page(width=w, height=h)
        if text is None:
            page.draw_rect(pymupdf.Rect(100, 100, 300, 200))
        else:
            page.insert_textbox(pymupdf.Rect(50, 50, w - 50, h - 50), text, fontname="china-s", fontsize=14)
    return doc


def make_pdf_bytes(pages: list[str | None], landscape: bool = False) -> bytes:
    doc = _build_pdf(pages, landscape)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def make_pdf(directory: Path, pages: list[str | None], landscape: bool = False, name: str = "doc.pdf") -> Path:
    path = directory / name
    path.write_bytes(make_pdf_bytes(pages, landscape))
    return path
