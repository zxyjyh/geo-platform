#!/usr/bin/env python3
"""用法：python3 analysis/quick_scan.py <round> <channel>，例如 trial api-custom
粗筛：按别名做字符串匹配，看三家平台的提及与先后。不是正式编码（正式编码见 docs/schema-v1.md §2.4），只用于试跑时快速看结果。"""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALIASES = {"澳觅": ["澳觅", "澳覓", "Aomi", "aomi", "AOMI"],
           "mFood": ["mFood", "MFood", "mfood", "澳門Food", "澳门Food"],
           "闪蜂": ["闪蜂", "閃蜂"]}


def first_pos(text, names):
    hits = [text.find(n) for n in names if n in text]
    return min(hits) if hits else None


def main(round_name, channel):
    qs = {q["qid"]: q for q in csv.DictReader(open(ROOT / "data/questions/questions-v4-50.csv", encoding="utf-8-sig"))}
    runs = [r for r in csv.DictReader(open(ROOT / f"data/runs/runs-{round_name}.csv", encoding="utf-8-sig"))
            if r["channel"] == channel]
    ids = {r["run_id"] for r in runs}
    srcs = [s for s in csv.DictReader(open(ROOT / f"data/runs/sources-{round_name}.csv", encoding="utf-8-sig"))
            if s["run_id"] in ids]
    print(f"== {round_name} / {channel} ==")
    print(f"{'qid':4} {'品牌':2} {'澳觅':4} {'mFood':5} {'闪蜂':4} 先后  信源 搜索  问题")
    nb = Counter()
    for r in sorted(runs, key=lambda r: r["qid"]):
        q = qs[r["qid"]]
        pos = {k: first_pos(r["answer_text"], v) for k, v in ALIASES.items()}
        order = ">".join(k for k, p in sorted(((k, p) for k, p in pos.items() if p is not None), key=lambda x: x[1]))
        mark = {k: ("Y" if p is not None else "-") for k, p in pos.items()}
        print(f"{r['qid']:4} {q['branded']:2}   {mark['澳觅']:4} {mark['mFood']:5} {mark['闪蜂']:4} {order or '无':12} "
              f"{r['sources_count']:>2} {r['search_calls']:>3}  {q['question']}")
        if q["branded"] == "N":
            nb["n"] += 1
            for k in ALIASES:
                nb[k] += mark[k] == "Y"
            nb["澳觅首位"] += order.startswith("澳觅")
    if nb["n"]:
        print(f"\n不带品牌名的题 n={nb['n']}（每题 1 次，粗筛）：澳觅 {nb['澳觅']}，mFood {nb['mFood']}，闪蜂 {nb['闪蜂']}，澳觅最先出现 {nb['澳觅首位']}")
    doms = Counter(s["domain"] for s in srcs)
    print(f"\n信源共 {len(srcs)} 条，{len(doms)} 个域名；前 15：")
    for d, c in doms.most_common(15):
        print(f"  {c:3}  {d}")
    tin = sum(int(r["input_tokens"] or 0) for r in runs); tout = sum(int(r["output_tokens"] or 0) for r in runs)
    print(f"\n用量：{len(runs)} 次调用，搜索 {sum(int(r['search_calls'] or 0) for r in runs)} 次，输入 {tin} tokens，输出 {tout} tokens")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
