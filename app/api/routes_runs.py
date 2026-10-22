from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.common import ModelPlatform, alias_version
from app.auth import current_user
from app.coding import ENTITIES, load_aliases, mention_snippet
from app.db import get_session
from app.models import Coding, Question, Run, Source, SourceTag

router = APIRouter(prefix="/runs", dependencies=[Depends(current_user)])


def _coding_json(c: Coding | None):
    if c is None:
        return None
    return {"alias_version": c.alias_version,
            "mention": {e: getattr(c, f"mention_{e}") for e in ENTITIES},
            "order": {e: getattr(c, f"order_{e}") for e in ENTITIES}}


@router.get("")
def list_runs(date_from: date | None = None, date_to: date | None = None, qid: str | None = None,
              channel: str | None = None, round: str | None = None, aomi_mentioned: bool | None = None,
              status: str | None = None, platform: ModelPlatform = "doubao", page: int = Query(1, ge=1),
              size: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    v = alias_version(session)
    q = (select(Run, Coding, Question.text, Question.scene)
         .outerjoin(Coding, (Coding.run_id == Run.run_id) & (Coding.alias_version == v))
         .outerjoin(Question, (Question.qid == Run.qid) & (Question.version == Run.question_version))
         .where(Run.platform == platform))
    if date_from:
        q = q.where(Run.collect_date >= date_from)
    if date_to:
        q = q.where(Run.collect_date <= date_to)
    for col, val in ((Run.qid, qid), (Run.channel, channel), (Run.round, round), (Run.status, status)):
        if val:
            q = q.where(col == val)
    if aomi_mentioned is not None:
        q = q.where(Coding.mention_aomi.is_(aomi_mentioned))
    total = session.scalar(select(func.count()).select_from(q.subquery()))
    rows = session.execute(q.order_by(Run.collect_date.desc(), Run.channel, Run.qid)
                           .offset((page - 1) * size).limit(size)).all()
    aomi_aliases = load_aliases(session, v)["aomi"]
    items = []
    for run, coding, text, scene in rows:
        cj = _coding_json(coding)
        items.append({"run_id": run.run_id, "collect_date": run.collect_date, "qid": run.qid, "question": text,
                      "scene": scene, "aomi_snippet": mention_snippet(run.answer_text, aomi_aliases),
                      "round": run.round, "channel": run.channel, "status": run.status,
                      "mention": cj["mention"] if cj else None, "order": cj["order"] if cj else None,
                      "sources_count": run.sources_count})
    return {"total": total, "items": items}


@router.get("/{run_id}")
def run_detail(run_id: str, session: Session = Depends(get_session)):
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "没有这条 run")
    coding = session.get(Coding, (run_id, alias_version(session)))
    q = session.get(Question, (run.qid, run.question_version))
    sources = list(session.scalars(select(Source).where(Source.run_id == run_id).order_by(Source.rank)))
    tagged = set(session.scalars(select(SourceTag.url_norm).where(
        SourceTag.tag == "external_geo", SourceTag.url_norm.in_([s.url_norm for s in sources]))))
    fields = {c.name: getattr(run, c.name) for c in Run.__table__.columns}
    return {**fields, "question": q.text if q else None, "coding": _coding_json(coding),
            "sources": [{"rank": s.rank, "title": s.title, "url": s.url, "url_norm": s.url_norm, "domain": s.domain,
                         "site_name": s.site_name, "publish_time_raw": s.publish_time_raw,
                         "publish_time": s.publish_time, "platform_key": s.platform_key, "is_owned": s.is_owned,
                         "external_geo": s.url_norm in tagged} for s in sources]}
