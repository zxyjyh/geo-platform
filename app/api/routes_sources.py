from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis import citation_lifecycle, domain_ranking, owned_citations, platform_counts
from app.api.common import MAX_SPAN_DAYS, ModelPlatform, api_channel, date_range, first_date, to_json
from app.auth import current_user
from app.collector import ROUND
from app.db import get_session
from app.models import Run, Source, SourceTag
from app.timeutil import today_cst
from app.urls import normalize_url

router = APIRouter(prefix="/sources", dependencies=[Depends(current_user)])


@router.get("/domains")
def domains(start: date | None = None, end: date | None = None, channel: str | None = None,
            platform: ModelPlatform = "doubao", session: Session = Depends(get_session)):
    start, end = date_range(start, end)
    return domain_ranking(session, api_channel(session, channel), start, end, platform=platform)


@router.get("/platforms")
def platforms(start: date | None = None, end: date | None = None, channel: str | None = None,
              platform: ModelPlatform = "doubao", session: Session = Depends(get_session)):
    start, end = date_range(start, end)
    return [to_json(p) for p in platform_counts(session, api_channel(session, channel), start, end,
                                                platform=platform)]


@router.get("/owned")
def owned(start: date | None = None, end: date | None = None, channel: str | None = None,
          platform: ModelPlatform = "doubao", session: Session = Depends(get_session)):
    start, end = date_range(start, end)
    return [{"run_id": s.run_id, "rank": s.rank, "title": s.title, "url": s.url, "domain": s.domain,
             "platform_key": s.platform_key}
            for s in owned_citations(session, api_channel(session, channel), start, end, platform)]


@router.get("/lifecycle")
def lifecycle(start: date | None = None, end: date | None = None, channel: str | None = None,
              platform: ModelPlatform = "doubao", session: Session = Depends(get_session)):
    """缺省窗口从该渠道第一天开始（最多一年），这样只有真正在监测开始那天就被引用的文章才标左删失。"""
    channel = api_channel(session, channel)
    end = end or today_cst()
    if start is None:
        first = first_date(session, channel, platform)
        start = max(first, end - timedelta(days=MAX_SPAN_DAYS - 1)) if first else end - timedelta(days=29)
        start = min(start, end)                  # end 早于渠道第一天：窗口里本来就没有数据
    start, end = date_range(start, end)
    return [to_json(c) for c in citation_lifecycle(session, channel, start, end, platform)]


@router.get("/top-articles")
def top_articles(start: date | None = None, end: date | None = None, channel: str | None = None,
                 platform: ModelPlatform = "doubao", limit: int = Query(20, ge=1, le=100),
                 session: Session = Depends(get_session)):
    """按 url_norm 聚合 sources，返回引用次数最多的文章。"""
    ch = api_channel(session, channel)
    start, end = date_range(start, end)

    # 聚合：引用次数、首次/末次引用日期
    agg_q = (
        select(
            Source.url_norm,
            func.count().label("citation_count"),
            func.min(Run.collect_date).label("first_seen"),
            func.max(Run.collect_date).label("last_seen"),
        )
        .join(Run, Run.run_id == Source.run_id)
        .where(Run.round == ROUND, Run.status == "valid", Run.platform == platform, Run.channel == ch,
               Run.collect_date >= start, Run.collect_date <= end)
        .group_by(Source.url_norm)
        .order_by(func.count().desc())
        .limit(limit)
    )
    agg_rows = session.execute(agg_q).all()
    if not agg_rows:
        return {"articles": []}

    # 取每个 url_norm 最新一条 source 的 title/url/domain/site_name
    top_norms = [r.url_norm for r in agg_rows]
    detail_q = (
        select(Source, Run.collect_date)
        .join(Run, Run.run_id == Source.run_id)
        .where(Run.round == ROUND, Run.status == "valid", Run.platform == platform, Run.channel == ch,
               Run.collect_date >= start, Run.collect_date <= end,
               Source.url_norm.in_(top_norms))
        .order_by(Source.url_norm, Run.collect_date.desc(), Source.rank)
    )
    details = {}
    for s, _ in session.execute(detail_q):
        if s.url_norm not in details:
            details[s.url_norm] = s

    articles = []
    for r in agg_rows:
        s = details.get(r.url_norm)
        articles.append({
            "url": s.url if s else "",
            "title": s.title if s else "",
            "domain": s.domain if s else "",
            "site_name": s.site_name if s else "",
            "citation_count": r.citation_count,
            "first_seen": r.first_seen.isoformat(),
            "last_seen": r.last_seen.isoformat(),
        })
    return {"articles": articles}


class TagBody(BaseModel):
    url: str
    tag: Literal["external_geo"]
    note: str = ""


@router.post("/tags")
def add_tag(body: TagBody, session: Session = Depends(get_session)):
    key = normalize_url(body.url)
    row = session.get(SourceTag, key)
    if row is None:
        session.add(SourceTag(url_norm=key, tag=body.tag, note=body.note))
    else:
        row.tag, row.note = body.tag, body.note
    session.commit()
    return {"url_norm": key, "tag": body.tag, "note": body.note}


@router.delete("/tags")
def delete_tag(url: str, session: Session = Depends(get_session)):
    key = normalize_url(url)
    row = session.get(SourceTag, key)
    if row is not None:
        session.delete(row)
        session.commit()
    return {"url_norm": key, "deleted": row is not None}
