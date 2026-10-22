"""当日指标、趋势和自检。口径见 spec §4.5：

- 题目范围：当前题库里不带品牌名的题；只取 round=daily、指定 channel 的 run；
- 分母：当天 status=valid 且有指定 alias_version 编码的 run 数。void、failed、缺失都进 missing_qids；
- 提及率 = 提到 e 的 run 数 / 分母；三家中首位率 = e 排第 1 的 run 数 / 分母；
- 提及份额 = 提到 e 的 run 数 / 三家提及次数之和。
"""
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.coding import ENTITIES
from app.collector import ROUND, setting
from app.models import Coding, Question, Run


@dataclass(frozen=True)
class Ratio:
    num: int
    den: int

    def pct(self) -> float | None:
        return None if self.den == 0 else self.num * 100 / self.den


@dataclass
class DailyMetrics:
    date: date
    channel: str
    n_expected: int
    n_valid: int
    missing_qids: list[str]
    mention: dict[str, Ratio]
    first: dict[str, Ratio]
    share: dict[str, Ratio]
    selfcheck_failures: list[str]


def unbranded_qids(session: Session) -> list[str]:
    version = setting(session, "question_version", "v3")
    return list(session.scalars(select(Question.qid).where(Question.version == version, Question.branded.is_(False))
                                .order_by(Question.qid)))


def daily_metrics(session: Session, d: date, channel: str, alias_version: int,
                  qids: list[str] | None = None, platform: str = "doubao") -> DailyMetrics:
    qids = unbranded_qids(session) if qids is None else qids
    rows = session.execute(
        select(Run, Coding)
        .outerjoin(Coding, (Coding.run_id == Run.run_id) & (Coding.alias_version == alias_version))
        .where(Run.round == ROUND, Run.collect_date == d, Run.platform == platform, Run.channel == channel,
               Run.qid.in_(qids))
    ).all()
    failures: list[str] = []
    cs: list[Coding] = []
    valid_qids: list[str] = []
    for run, coding in rows:
        if run.status != "valid":
            continue
        if coding is None:
            failures.append("coding_missing")       # valid 的 run 没有这个版本的编码：说明重算没跑完
            continue
        cs.append(coding)
        valid_qids.append(run.qid)
    n_valid = len(cs)
    mention = {e: Ratio(sum(getattr(c, f"mention_{e}") for c in cs), n_valid) for e in ENTITIES}
    first = {e: Ratio(sum(getattr(c, f"order_{e}") == 1 for c in cs), n_valid) for e in ENTITIES}
    total = sum(r.num for r in mention.values())
    share = {e: Ratio(mention[e].num, total) for e in ENTITIES}

    # 自检。"不混渠道"由查询条件保证，"份额分子之和 = 分母"是代数恒等式，都不另设检查（写了也永远不会失败）
    for e in ENTITIES:
        if first[e].num > mention[e].num:
            failures.append(f"first_{e}")
    if len(valid_qids) != len(set(valid_qids)):
        failures.append("duplicate_qid")            # 同一天同一题多条 valid：分母会被多算
    if n_valid > len(qids):
        failures.append("n_valid")

    return DailyMetrics(date=d, channel=channel, n_expected=len(qids), n_valid=n_valid,
                        missing_qids=[q for q in qids if q not in set(valid_qids)], mention=mention, first=first,
                        share=share, selfcheck_failures=sorted(set(failures)))


def trend(session: Session, start: date, end: date, channel: str, alias_version: int,
          platform: str = "doubao") -> list[DailyMetrics]:
    """每天一条，没有数据的日期也输出（n_valid=0），前端据此显示"缺数据"。"""
    qids = unbranded_qids(session)
    out, d = [], start
    while d <= end:
        out.append(daily_metrics(session, d, channel, alias_version, qids, platform))
        d += timedelta(days=1)
    return out
