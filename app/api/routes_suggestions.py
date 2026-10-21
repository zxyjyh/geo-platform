from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analysis import platform_counts, reference_articles, weak_questions
from app.api.common import alias_version, api_channel, latest_date, to_json
from app.auth import current_user
from app.collector import setting
from app.db import get_session
from app.timeutil import today_cst

router = APIRouter(prefix="/suggestions", dependencies=[Depends(current_user)])


@router.get("")
def suggestions(channel: str | None = None, session: Session = Depends(get_session)):
    channel = api_channel(session, channel)
    today = latest_date(session, channel) or today_cst()
    window = int(setting(session, "platform_window_days", "30"))
    items = []
    for w in weak_questions(session, channel, today, recent_n=int(setting(session, "weak_recent_n", "7")),
                            mention_ratio=float(setting(session, "weak_mention_ratio", "0.5")),
                            alias_version=alias_version(session)):
        items.append({
            "weak": to_json(w),
            "platforms": [to_json(p) for p in platform_counts(session, channel, today - timedelta(days=window - 1),
                                                              today, qids=[w.qid])],
            "references": [to_json(a) for a in reference_articles(session, w.qid, channel, today, days=window)],
        })
    return {"channel": channel, "date": today, "notice": f"排序来自 {channel} 渠道的信源，App 可能不同。",
            "items": items}
