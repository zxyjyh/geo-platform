"""信源分析和优化建议。只看 round=daily、status=valid 的 run，按渠道分开统计（spec §4.6、§4.7）。"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collector import ROUND
from app.metrics import unbranded_qids
from app.models import Coding, Platform, Question, Run, Source, SourceTag
from app.urls import host_key


def growth_index(values: list[float]) -> float:
    """对时间序列做线性回归，返回斜率。

    values 是按时间顺序排列的数值（如每天的可见度）。
    用 numpy polyfit(1) 拟合一次多项式，返回斜率。
    不足 2 个数据点返回 0.0。
    """
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values))
    slope, _ = np.polyfit(x, values, 1)
    result = round(float(slope), 4)
    # Normalize -0.0 to 0.0 to avoid displaying "-0.00"
    return 0.0 if result == 0.0 else result


def _daily_sources(channel: str, start: date, end: date, platform: str = "doubao"):
    return (select(Source).join(Run, Run.run_id == Source.run_id)
            .where(Run.round == ROUND, Run.status == "valid", Run.platform == platform, Run.channel == channel,
                   Run.collect_date >= start, Run.collect_date <= end))


def domain_ranking(session: Session, channel: str, start: date, end: date, limit: int = 50,
                   platform: str = "doubao") -> list[tuple[str, int]]:
    """域名去掉 www. / m. 再计数，m.sohu.com 和 www.sohu.com 算同一个站。"""
    c = Counter(host_key(s.domain) for s in session.scalars(_daily_sources(channel, start, end, platform)))
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


@dataclass
class PlatformCount:
    key: str
    name: str
    count: int
    verified: bool
    review_strictness: str
    allows_links: str
    notes: str


def platform_counts(session: Session, channel: str, start: date, end: date,
                    qids: list[str] | None = None, platform: str = "doubao") -> list[PlatformCount]:
    """固定返回全部可发布平台，count 为 0 的也列出（verified=False，前端显示"未验证"）。

    只按被引用次数排序；平台属性（审核宽严等）只随结果带出去展示，不参与排序（spec §4.6.2）。"""
    q = _daily_sources(channel, start, end, platform).where(Source.platform_key.is_not(None))
    if qids is not None:
        q = q.where(Run.qid.in_(qids))
    c = Counter(s.platform_key for s in session.scalars(q))
    platforms = session.scalars(select(Platform).where(Platform.publishable.is_(True)).order_by(Platform.key))
    out = [PlatformCount(key=p.key, name=p.name, count=c[p.key], verified=c[p.key] > 0,
                         review_strictness=p.review_strictness, allows_links=p.allows_links, notes=p.notes)
           for p in platforms]
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
                   alias_version: int = 1, platform: str = "doubao") -> list[WeakQuestion]:
    """每道不带品牌名的题取最近 recent_n 条 valid 的 daily run，只返回至少命中一条短板原因的题。

    按条数取，不按天数：每题每天问 2 次时，最近 recent_n 条只覆盖一半的天数。"""
    out = []
    for qid in unbranded_qids(session):
        cs = list(session.scalars(
            select(Coding).join(Run, Run.run_id == Coding.run_id)
            .where(Run.round == ROUND, Run.status == "valid", Run.platform == platform, Run.channel == channel,
                   Run.qid == qid,
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
                       limit: int = 5, platform: str = "doubao") -> list[RefArticle]:
    """按 url_norm 分组，count = 引用过它的 run 数；url / title 取最近一次出现时的值。"""
    rows = session.execute(
        _daily_sources(channel, end - timedelta(days=days - 1), end, platform).add_columns(Run.collect_date, Run.collected_at)
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


def owned_citations(session: Session, channel: str, start: date, end: date, platform: str = "doubao") -> list[Source]:
    return list(session.scalars(_daily_sources(channel, start, end, platform).where(Source.is_owned.is_(True))
                                .order_by(Run.collect_date.desc(), Source.rank)))


@dataclass
class CitationLife:
    url_norm: str
    url: str
    title: str
    domain: str
    platform_key: str | None
    n_citations: int             # 引用过它的回答数（同一条回答里出现多次算一次）
    first_date: date
    last_date: date
    active_days: int             # 有被引用的天数
    span_days: int               # 首次到末次的天数（含两端）
    persistence: float           # 持续度 = active_days / span_days
    energy: float                # 日均被引 = n_citations / active_days
    publish_time: datetime | None
    lag_days: int | None         # 首次被引耗时 = first_date − 发布日期；左删失或发布时间可疑时为 None
    left_censored: bool          # 首次被引日 = 窗口内第一个可观测日：监测开始前可能已被引用
    publish_suspect: bool        # 发布时间晚于首次被引
    external_geo: bool
    is_owned: bool


def citation_lifecycle(session: Session, channel: str, start: date, end: date,
                       platform: str = "doubao") -> list[CitationLife]:
    """每篇文章（url_norm）在窗口内的引用周期（spec §4.6.1）。

    窗口第一个可观测日 = max(start, 该渠道历史上第一个有 valid daily run 的日子)；首次被引日等于它时
    标左删失，不算首次被引耗时。url / title / domain / platform_key 取最近一次出现时的值。
    """
    channel_first = session.scalar(select(func.min(Run.collect_date)).where(
        Run.round == ROUND, Run.status == "valid", Run.platform == platform, Run.channel == channel))
    if channel_first is None:
        return []
    observable_from = max(start, channel_first)
    rows = session.execute(_daily_sources(channel, start, end, platform)
                           .add_columns(Run.collect_date, Run.collected_at)).all()
    groups: dict[str, dict] = {}
    for s, collect_date, collected_at in rows:
        g = groups.setdefault(s.url_norm, {"runs": set(), "days": set(), "latest": None, "at": None,
                                           "publish": None, "owned": False})
        g["runs"].add(s.run_id)
        g["days"].add(collect_date)
        g["owned"] = g["owned"] or s.is_owned
        if s.publish_time is not None and (g["publish"] is None or s.publish_time < g["publish"]):
            g["publish"] = s.publish_time
        at = (collect_date, collected_at, -s.rank)
        if g["at"] is None or at > g["at"]:
            g["latest"], g["at"] = s, at
    tagged = set(session.scalars(select(SourceTag.url_norm).where(SourceTag.tag == "external_geo",
                                                                  SourceTag.url_norm.in_(list(groups)))))
    out = []
    for k, g in groups.items():
        first, last = min(g["days"]), max(g["days"])
        span = (last - first).days + 1
        censored = first == observable_from
        lag = None if g["publish"] is None else (first - g["publish"].date()).days
        suspect = lag is not None and lag < 0
        latest = g["latest"]
        out.append(CitationLife(
            url_norm=k, url=latest.url, title=latest.title, domain=latest.domain, platform_key=latest.platform_key,
            n_citations=len(g["runs"]), first_date=first, last_date=last, active_days=len(g["days"]),
            span_days=span, persistence=len(g["days"]) / span, energy=len(g["runs"]) / len(g["days"]),
            publish_time=g["publish"], lag_days=None if censored or suspect else lag, left_censored=censored,
            publish_suspect=suspect, external_geo=k in tagged, is_owned=g["owned"]))
    out.sort(key=lambda c: (-c.n_citations, c.first_date, c.url_norm))
    return out
