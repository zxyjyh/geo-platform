#!/usr/bin/env python3
"""豆包 API 联网搜索采集：按 docs/schema-v1.md 写 runs / sources 两张表，并保存原始响应。

两种联网方式（火山方舟文档「联网搜索工具」，2026-10-20 读取）：
  plugin  联网内容插件：默认全网，可选 toutiao/douyin/moji 来源，user_location 生效
  custom  豆包搜索 Custom 版：sources 只能是 ["doubao"]，user_location 会被忽略
两者都不是豆包 App，数据只能和 App 分开统计。

用法：
  export ARK_API_KEY=...
  python3 collect/doubao_api.py --round pairing --rep 1 --variant plugin --qids Q01,Q10 --dry-run
  python3 collect/doubao_api.py --round baseline --rep 1 --variant plugin
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/responses"
DEFAULT_MODEL = "doubao-seed-2-1-pro-260915"
ROOT = Path(__file__).resolve().parent.parent
CST = timezone(timedelta(hours=8))

RUN_FIELDS = ["run_id", "round", "qid", "question_version", "platform", "channel", "channel_detail", "mode",
              "collected_at", "collector", "account_ref", "location", "new_session", "answer_text",
              "answer_capture", "sources_visible", "sources_count", "status",
              "search_queries", "search_calls", "input_tokens", "output_tokens"]
SOURCE_FIELDS = ["run_id", "rank", "title", "url", "domain", "site_name", "publish_time", "source_type", "is_owned"]


def build_body(question, variant, model, location, limit, max_tool_calls):
    if variant == "custom":
        tool = {"type": "web_search", "sources": ["doubao"]}
    else:
        tool = {"type": "web_search", "limit": limit}
        if location:
            # 字段名来自文档；country/region 的取值格式（中文名还是代码）文档未写明，首次实测后确认
            tool["user_location"] = {"type": "approximate", "country": location[0],
                                     "region": location[1], "city": location[2]}
    return {
        "model": model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": question}]}],
        "tools": [tool],
        "max_tool_calls": max_tool_calls,
    }


def parse_response(resp):
    """返回 (answer_text, citations)。citations 按出现顺序去重（同一 url 只记一次）。"""
    texts, citations, seen = [], [], set()
    for item in resp.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") != "output_text":
                continue
            texts.append(part.get("text", ""))
            for ann in part.get("annotations", []) or []:
                if ann.get("type") != "url_citation" or ann.get("url") in seen:
                    continue
                seen.add(ann.get("url"))
                citations.append(ann)
    return "".join(texts), citations


def search_queries(resp):
    """模型实际发出的搜索词（web_search_call.action.query，文档未写，2026-10-21 实测发现）。"""
    return [item.get("action", {}).get("query", "") for item in resp.get("output", [])
            if item.get("type") == "web_search_call"]


def call_api(body, api_key, timeout=180):
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def append_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


def drop_channel_rows(path, fields, is_this_channel):
    """重建前只删掉本渠道的行，同一轮里其他渠道的数据保留。"""
    if not path.exists():
        return
    keep = [r for r in csv.DictReader(open(path, encoding="utf-8-sig")) if not is_this_channel(r)]
    path.unlink()
    if keep:
        append_csv(path, fields, keep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True, help="pairing / baseline / R1 / R2 …")
    ap.add_argument("--rep", type=int, required=True, help="本题在本轮的第几次（1–3），每次放在不同日期跑")
    ap.add_argument("--variant", choices=["plugin", "custom"], default="plugin")
    ap.add_argument("--questions", default=str(ROOT / "data/questions/questions-v4-50.csv"))
    ap.add_argument("--qversion", default="v4")
    ap.add_argument("--qids", help="逗号分隔，默认全部")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--location", default="中国,广东,深圳", help="country,region,city；仅 plugin 生效")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--max-tool-calls", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=1.0, help="两次调用之间的间隔秒数")
    ap.add_argument("--dry-run", action="store_true", help="只打印请求体，不调用")
    ap.add_argument("--reparse", action="store_true", help="不调用 API，用已保存的原始响应重建本轮 CSV")
    args = ap.parse_args()

    questions = list(csv.DictReader(open(args.questions, encoding="utf-8-sig")))
    if args.qids:
        wanted = set(args.qids.split(","))
        questions = [q for q in questions if q["qid"] in wanted]
        missing = wanted - {q["qid"] for q in questions}
        if missing:
            sys.exit(f"题库里没有这些题号：{sorted(missing)}")
    location = tuple(args.location.split(",")) if args.location else None
    if location and len(location) != 3:
        sys.exit("--location 要写成 country,region,city")

    api_key = os.environ.get("ARK_API_KEY")
    if not (args.dry_run or args.reparse) and not api_key:
        sys.exit("缺少环境变量 ARK_API_KEY")

    channel = f"api-{args.variant}"
    loc_label = "/".join(location) if (location and args.variant == "plugin") else "未设置"
    runs_path = ROOT / "data/runs" / f"runs-{args.round}.csv"
    sources_path = ROOT / "data/runs" / f"sources-{args.round}.csv"
    raw_dir = ROOT / "data/raw" / args.round
    if args.reparse:
        drop_channel_rows(runs_path, RUN_FIELDS, lambda r: r["channel"] == channel)
        drop_channel_rows(sources_path, SOURCE_FIELDS, lambda r: f"-doubao-{channel}-" in r["run_id"])

    for i, q in enumerate(questions):
        body = build_body(q["question"], args.variant, args.model, location, args.limit, args.max_tool_calls)
        run_id = f"{args.round}-doubao-{channel}-{q['qid']}-{args.rep}"
        if args.dry_run:
            print(run_id, json.dumps(body, ensure_ascii=False))
            continue
        raw_path = raw_dir / f"{run_id}.json"
        if args.reparse:
            if not raw_path.exists():
                continue
            saved = json.loads(raw_path.read_text(encoding="utf-8"))
            resp, collected_at = saved["response"], saved["collected_at"]
        elif raw_path.exists():
            print(f"跳过 {run_id}：已采集过")
            continue
        else:
            collected_at = datetime.now(CST).isoformat(timespec="seconds")
            try:
                resp = call_api(body, api_key)
            except urllib.error.HTTPError as e:
                print(f"{run_id} 失败 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}", file=sys.stderr)
                continue
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"{run_id} 失败: {e}", file=sys.stderr)
                continue
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(
                json.dumps({"request": body, "response": resp, "collected_at": collected_at}, ensure_ascii=False, indent=1),
                encoding="utf-8")
        text, cites = parse_response(resp)
        queries = search_queries(resp)
        usage = resp.get("usage", {})
        append_csv(runs_path, RUN_FIELDS, [{
            "run_id": run_id, "round": args.round, "qid": q["qid"], "question_version": args.qversion,
            "platform": "doubao", "channel": channel,
            "channel_detail": f"{args.model} / web_search {args.variant}",
            "mode": "联网", "collected_at": collected_at, "collector": "collect/doubao_api.py",
            "account_ref": "ark-default", "location": loc_label, "new_session": "Y",
            "answer_text": text, "answer_capture": f"data/raw/{args.round}/{run_id}.json",
            "sources_visible": "Y" if cites else "N", "sources_count": len(cites),
            "status": "valid" if text else "void",
            "search_queries": " | ".join(queries), "search_calls": len(queries),
            "input_tokens": usage.get("input_tokens", ""), "output_tokens": usage.get("output_tokens", ""),
        }])
        append_csv(sources_path, SOURCE_FIELDS, [{
            "run_id": run_id, "rank": k + 1, "title": c.get("title", ""), "url": c.get("url", ""),
            "domain": urlparse(c.get("url", "")).netloc, "site_name": c.get("site_name", ""),
            "publish_time": c.get("publish_time", ""), "source_type": "", "is_owned": "",
        } for k, c in enumerate(cites)])
        print(f"{run_id} ok：回答 {len(text)} 字，信源 {len(cites)} 条，搜索 {len(queries)} 次")
        if not args.reparse and i < len(questions) - 1:
            time.sleep(args.sleep)


if __name__ == "__main__":
    main()
