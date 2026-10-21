#!/usr/bin/env python3
"""对照两轮采集：逐题比较信源域名的 Jaccard 和澳觅是否被提及。

用途（spec §4.3"上线后第一件事"）：api-custom 会忽略 user_location，可能改用调用方 IP 判断地区。
在服务器上跑一轮 daily，再和本机的 trial 对比；Jaccard 明显偏低或澳觅提及不一致，就要在看板注明地区取决于服务器所在地。

用法：python scripts/compare_rounds.py --a-round trial --b-date 2026-10-22 --channel api-custom
"""
import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.collector import setting  # noqa: E402
from app.models import Coding, Run, Source  # noqa: E402
from app.urls import host_key  # noqa: E402


@dataclass
class Row:
    qid: str
    jaccard: float | None
    domains_a: int
    domains_b: int
    aomi_a: bool | None
    aomi_b: bool | None


def _side(session: Session, runs: list[Run], version: int) -> dict[str, tuple[set[str], bool | None]]:
    out = {}
    for r in runs:
        doms = {host_key(d) for d in session.scalars(select(Source.domain).where(Source.run_id == r.run_id))}
        c = session.get(Coding, (r.run_id, version))
        out[r.qid] = (doms, None if c is None else c.mention_aomi)
    return out


def compare(session: Session, a_round: str, b_date: date, channel: str) -> list[Row]:
    version = int(setting(session, "alias_version", "1"))
    a_runs = session.scalars(select(Run).where(Run.round == a_round, Run.channel == channel, Run.status == "valid"))
    b_runs = session.scalars(select(Run).where(Run.round == "daily", Run.collect_date == b_date,
                                               Run.channel == channel, Run.status == "valid"))
    a, b = _side(session, list(a_runs), version), _side(session, list(b_runs), version)
    rows = []
    for qid in sorted(set(a) | set(b)):
        da, ma = a.get(qid, (set(), None))
        db, mb = b.get(qid, (set(), None))
        union = da | db
        rows.append(Row(qid=qid, jaccard=(len(da & db) / len(union)) if union else None,
                        domains_a=len(da), domains_b=len(db), aomi_a=ma, aomi_b=mb))
    return rows


def main() -> None:
    from app.config import get_settings
    from app.db import make_engine

    ap = argparse.ArgumentParser()
    ap.add_argument("--a-round", default="trial")
    ap.add_argument("--b-date", required=True)
    ap.add_argument("--channel", default="api-custom")
    args = ap.parse_args()
    with sessionmaker(make_engine(get_settings().database_url))() as s:
        rows = compare(s, args.a_round, date.fromisoformat(args.b_date), args.channel)
    print(f"{'qid':4} {'Jaccard':>7} {'A域名':>5} {'B域名':>5}  澳觅 A/B")
    for r in rows:
        j = "—" if r.jaccard is None else f"{r.jaccard:.2f}"
        flag = "" if r.aomi_a == r.aomi_b else "  ← 不一致"
        print(f"{r.qid:4} {j:>7} {r.domains_a:>5} {r.domains_b:>5}  {r.aomi_a}/{r.aomi_b}{flag}")
    js = [r.jaccard for r in rows if r.jaccard is not None]
    both = [r for r in rows if r.aomi_a is not None and r.aomi_b is not None]
    agree = sum(r.aomi_a == r.aomi_b for r in both)
    print(f"\n逐题 Jaccard 均值 {sum(js) / len(js):.2f}（{len(js)} 题）" if js else "\n没有可比的题")
    print(f"澳觅是否被提及一致：{agree}/{len(both)}")


if __name__ == "__main__":
    main()
