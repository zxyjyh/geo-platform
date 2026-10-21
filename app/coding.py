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
