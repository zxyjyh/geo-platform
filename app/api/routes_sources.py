from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.analysis import domain_ranking, owned_citations, platform_counts
from app.api.common import ModelPlatform, api_channel, date_range, to_json
from app.auth import current_user
from app.db import get_session
from app.models import SourceTag
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
