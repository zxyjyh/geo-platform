"""信源分析和优化建议。只看 round=daily、status=valid 的 run，按渠道分开统计（spec §4.6、§4.7）。"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector import ROUND
from app.metrics import unbranded_qids
from app.models import Coding, Platform, Question, Run, Source, SourceTag
from app.urls import host_key


def _daily_sources(channel: str, start: date, end: date):
    return (select(Source).join(Run, Run.run_id == Source.run_id)
            .where(Run.round == ROUND, Run.status == "valid", Run.channel == channel,
                   Run.collect_date >= start, Run.collect_date <= end))


def domain_ranking(session: Session, channel: str, start: date, end: date, limit: int = 50) -> list[tuple[str, int]]:
    """域名去掉 www. / m. 再计数，m.sohu.com 和 www.sohu.com 算同一个站。"""
    c = Counter(host_key(s.domain) for s in session.scalars(_daily_sources(channel, start, end)))
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


@dataclass
class PlatformCount:
    key: str
    name: str
    count: int
    verified: bool


def platform_counts(session: Session, channel: str, start: date, end: date,
                    qids: list[str] | None = None) -> list[PlatformCount]:
    """固定返回全部可发布平台，count 为 0 的也列出（verified=False，前端显示"未验证"）。"""
    q = _daily_sources(channel, start, end).where(Source.platform_key.is_not(None))
    if qids is not None:
        q = q.where(Run.qid.in_(qids))
    c = Counter(s.platform_key for s in session.scalars(q))
    platforms = session.scalars(select(Platform).where(Platform.publishable.is_(True)).order_by(Platform.key))
    out = [PlatformCount(key=p.key, name=p.name, count=c[p.key], verified=c[p.key] > 0) for p in platforms]
    return sorted(out, key=lambda p: -p.count)


@dataclass
class WeakQuestion:
    qid: str
    text: str
    n_runs: int
    aomi_mentions: int
    aomi_first: int
    competitor_first: int
    reasons: list[str] = field(default_factory=list)


def weak_questions(session: Session, channel: str, today: date, recent_n: int = 7, mention_ratio: float = 0.5,
                   alias_version: int = 1) -> list[WeakQuestion]:
    """每道不带品牌名的题取最近 recent_n 条 valid 的 daily run，只返回至少命中一条短板原因的题。"""
    out = []
    for qid in unbranded_qids(session):
        cs = list(session.scalars(
            select(Coding).join(Run, Run.run_id == Coding.run_id)
            .where(Run.round == ROUND, Run.status == "valid", Run.channel == channel, Run.qid == qid,
                   Run.collect_date <= today, Coding.alias_version == alias_version)
            .order_by(Run.collect_date.desc()).limit(recent_n)))
        if not cs:
            continue
        w = WeakQuestion(qid=qid, text="", n_runs=len(cs),
                         aomi_mentions=sum(c.mention_aomi for c in cs),
                         aomi_first=sum(c.order_aomi == 1 for c in cs),
                         competitor_first=sum(c.order_mfood == 1 or c.order_shanfeng == 1 for c in cs))
        if w.aomi_mentions < mention_ratio * w.n_runs:
            w.reasons.append("mention_low")
        if w.competitor_first > w.aomi_first:
            w.reasons.append("competitor_ahead")
        if w.reasons:
            run = session.get(Run, cs[0].run_id)
            q = session.get(Question, (qid, run.question_version))
            w.text = q.text if q else ""
            out.append(w)
    return out


@dataclass
class RefArticle:
    url_norm: str
    url: str
    title: str
    domain: str
    platform_key: str | None
    count: int
    external_geo: bool


def reference_articles(session: Session, qid: str, channel: str, end: date, days: int = 30,
                       limit: int = 5) -> list[RefArticle]:
    """按 url_norm 分组，count = 引用过它的 run 数；url / title 取最近一次出现时的值。"""
    rows = session.execute(
        _daily_sources(channel, end - timedelta(days=days - 1), end).add_columns(Run.collect_date, Run.collected_at)
        .where(Run.qid == qid)).all()
    groups: dict[str, dict] = {}
    for s, collect_date, collected_at in rows:
        g = groups.setdefault(s.url_norm, {"runs": set(), "latest": None, "at": None})
        g["runs"].add(s.run_id)
        # 先比 collect_date：补跑往日时 collected_at 是补跑当下，不能算"更近"
        at = (collect_date, collected_at, -s.rank)
        if g["at"] is None or at > g["at"]:
            g["latest"], g["at"] = s, at
    tagged = set(session.scalars(select(SourceTag.url_norm).where(SourceTag.tag == "external_geo",
                                                                  SourceTag.url_norm.in_(list(groups)))))
    out = [RefArticle(url_norm=k, url=g["latest"].url, title=g["latest"].title, domain=g["latest"].domain,
                      platform_key=g["latest"].platform_key, count=len(g["runs"]), external_geo=k in tagged)
           for k, g in groups.items()]
    out.sort(key=lambda a: (-a.count, -groups[a.url_norm]["at"][0].toordinal(), a.url_norm))
    return out[:limit]


def owned_citations(session: Session, channel: str, start: date, end: date) -> list[Source]:
    return list(session.scalars(_daily_sources(channel, start, end).where(Source.is_owned.is_(True))
                                .order_by(Run.collect_date.desc(), Source.rank)))
