#!/usr/bin/env python3
"""知识库验收题评测：逐题查一遍，看期望的那段原文是否出现在前 k 条里（spec §4.8）。

命中 = 前 k 条里有切片满足页码相等（expect_half 非空时半页也相等），且期望原文（规范化后）是切片原文的子串。
expect_page 为空的题只记录、不计入命中率，但仍打印最靠前的一条，方便人工判断是不是不相干的段落。

用法：uv run python -m scripts.kb_eval [--k 5] [--csv data/kb/eval-questions.csv]
"""
import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import ROOT  # noqa: E402
from app.kb.search import search  # noqa: E402
from app.kb.text import normalize  # noqa: E402

DEFAULT_CSV = ROOT / "data" / "kb" / "eval-questions.csv"


@dataclass
class EvalRow:
    qid: str
    question: str
    counted: bool  # 有 expect_page 才计入命中率
    rank: int | None  # 命中的名次（从 1 开始）；没命中为 None
    top: tuple[int, str, str] | None  # 第一条的 (页码, 半页, 原文)；查不到为 None


def load_rows(path: Path = DEFAULT_CSV) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _is_hit(hit, row: dict) -> bool:
    if hit.page_no != int(row["expect_page"]):
        return False
    if row["expect_half"] and hit.half != row["expect_half"]:
        return False
    return normalize(row["expect_text"]) in normalize(hit.text)


def evaluate(session: Session, rows: list[dict], embedder, k: int = 5) -> list[EvalRow]:
    out = []
    for row in rows:
        hits = search(session, row["question"], embedder, limit=k)
        counted = bool(row["expect_page"])
        rank = next((i for i, h in enumerate(hits, 1) if _is_hit(h, row)), None) if counted else None
        top = (hits[0].page_no, hits[0].half, hits[0].text) if hits else None
        out.append(EvalRow(row["qid"], row["question"], counted, rank, top))
    return out


def _brief(top: tuple[int, str, str] | None) -> str:
    if top is None:
        return "（无结果）"
    page, half, text = top
    return f"p{page}{half} {text[:40]!r}"


def main() -> None:
    from app.config import get_settings
    from app.db import make_engine
    from app.kb.embed import HttpArkEmbedder

    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = ap.parse_args()
    cfg = get_settings()
    rows = load_rows(args.csv)
    with sessionmaker(make_engine(cfg.database_url))() as s:
        results = evaluate(s, rows, HttpArkEmbedder(cfg.ark_api_key), args.k)
    print("注意：题目为草稿，待用户确认后定稿；及格线也待和用户一起定。\n")
    for r in results:
        if r.counted:
            mark = f"第 {r.rank} 名" if r.rank else f"未进前 {args.k}"
            print(f"{r.qid} {mark:8} {r.question}  | 第一条 {_brief(r.top)}")
        else:
            print(f"{r.qid} 仅记录   {r.question}  | 第一条 {_brief(r.top)}")
    counted = [r for r in results if r.counted]
    print(f"\n命中率 {sum(r.rank is not None for r in counted)}/{len(counted)}（前 {args.k} 条；仅记录的题不计入）")


if __name__ == "__main__":
    main()
