"""品牌归因（spec §4.4.1）：提到澳觅的回答里，有没有给出官方入口、有没有引用澳觅自有内容。

- 题目范围：当天该渠道全部题（含带品牌名的），只取 round=daily、status=valid；
- 分母：当前 alias_version 编码里 mention_aomi 为真的回答数；
- 正文给出官方入口：回答正文命中当前版本官方标识清单中任一条；网址等不区分大小写，电话只比数字；
- 信源含自有内容：该回答的信源里有 is_owned 的。
清单为空时 configured=False，前端显示"未配置官方标识"，不显示 0/n。
"""
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector import ROUND, setting
from app.metrics import Ratio
from app.models import BrandMark, Coding, Run, Source

MARK_KINDS = ("website", "phone", "app_store", "mini_program", "official_account", "other")


def _phone_re(value: str) -> re.Pattern:
    # 数字之间允许空格、短横线、括号；前后不能紧挨数字，免得订单号、价格里的一段被当成电话
    digits = re.sub(r"\D", "", value)
    return re.compile(r"(?<!\d)" + r"[\s\-()]*".join(digits) + r"(?!\d)")


def match_marks(text: str, marks: list[BrandMark]) -> list[BrandMark]:
    lower = text.lower()
    return [m for m in marks
            if (_phone_re(m.value).search(text) if m.kind == "phone" else m.value.lower() in lower)]


@dataclass
class AttributionHit:
    run_id: str
    qid: str
    marks: list[str]
    owned_source: bool


@dataclass
class AttributionDay:
    date: date
    channel: str
    version: int
    configured: bool
    text: Ratio
    source: Ratio
    hits: list[AttributionHit]


def current_marks(session: Session) -> tuple[int, list[BrandMark]]:
    version = int(setting(session, "brand_mark_version", "0"))
    return version, list(session.scalars(select(BrandMark).where(BrandMark.version == version).order_by(BrandMark.id)))


def attribution_daily(session: Session, d: date, channel: str, alias_version: int,
                      platform: str = "doubao") -> AttributionDay:
    version, marks = current_marks(session)
    runs = list(session.scalars(
        select(Run).join(Coding, (Coding.run_id == Run.run_id) & (Coding.alias_version == alias_version))
        .where(Run.round == ROUND, Run.collect_date == d, Run.platform == platform, Run.channel == channel,
               Run.status == "valid", Coding.mention_aomi.is_(True))
        .order_by(Run.qid, Run.rep)))
    owned = set(session.scalars(select(Source.run_id).where(Source.run_id.in_([r.run_id for r in runs]),
                                                            Source.is_owned.is_(True))))
    hits = [AttributionHit(run_id=r.run_id, qid=r.qid, marks=[m.value for m in match_marks(r.answer_text, marks)],
                           owned_source=r.run_id in owned) for r in runs]
    n = len(hits)
    return AttributionDay(date=d, channel=channel, version=version, configured=bool(marks),
                          text=Ratio(sum(bool(h.marks) for h in hits), n),
                          source=Ratio(sum(h.owned_source for h in hits), n), hits=hits)
