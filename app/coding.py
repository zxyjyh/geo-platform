"""编码：用别名表做字符串匹配，判断三家有没有被提及、谁先出现。规则见 spec §4.4。"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alias

ENTITIES = ("aomi", "mfood", "shanfeng")


@dataclass
class CodingResult:
    mention: dict[str, bool]
    order: dict[str, int | None]


def code_answer(text: str, aliases: dict[str, list[str]]) -> CodingResult:
    """每家取所有别名里最早出现的位置；排位只在被提及的几家之间按位置排，从 1 开始。"""
    pos: dict[str, int] = {}
    for e in ENTITIES:
        hits = [i for i in (text.find(a) for a in aliases.get(e, []) if a) if i >= 0]
        if hits:
            pos[e] = min(hits)
    ranked = sorted(pos, key=lambda e: pos[e])
    return CodingResult(mention={e: e in pos for e in ENTITIES},
                        order={e: (ranked.index(e) + 1 if e in pos else None) for e in ENTITIES})


def load_aliases(session: Session, version: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {e: [] for e in ENTITIES}
    for a in session.scalars(select(Alias).where(Alias.version == version).order_by(Alias.id)):
        out.setdefault(a.entity, []).append(a.alias)
    return out


def _coding_for(run, aliases: dict[str, list[str]], alias_version: int):
    from app.models import Coding

    r = code_answer(run.answer_text, aliases)
    return Coding(run_id=run.run_id, alias_version=alias_version,
                  mention_aomi=r.mention["aomi"], mention_mfood=r.mention["mfood"],
                  mention_shanfeng=r.mention["shanfeng"], order_aomi=r.order["aomi"],
                  order_mfood=r.order["mfood"], order_shanfeng=r.order["shanfeng"])


def recode_all(session: Session, alias_version: int) -> int:
    """用指定版本的别名表给所有 valid 的 run 重新编码，写入该版本的 Coding（旧版本保留）。返回编码条数。"""
    from app.models import Coding, Run

    aliases = load_aliases(session, alias_version)
    session.query(Coding).filter(Coding.alias_version == alias_version).delete()
    n = 0
    for run in session.scalars(select(Run).where(Run.status == "valid")):
        session.add(_coding_for(run, aliases, alias_version))
        n += 1
    session.commit()
    return n


def backfill_missing(session: Session, alias_version: int) -> int:
    """给缺少该版本编码的 valid run 补编码。别名表升版本和采集并发时，空窗里入库的 run 只有旧版本编码，靠它补齐。"""
    from app.models import Coding, Run

    has = select(Coding.run_id).where(Coding.alias_version == alias_version)
    runs = list(session.scalars(select(Run).where(Run.status == "valid", Run.run_id.not_in(has))))
    if not runs:
        return 0
    aliases = load_aliases(session, alias_version)
    session.add_all(_coding_for(run, aliases, alias_version) for run in runs)
    session.commit()
    return len(runs)
