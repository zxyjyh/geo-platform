"""导入 trial 那一轮：从原始 JSON 重新解析（不读 CSV 里的 answer_text），和日常采集走同一套解析。

trial 的 CSV 里 question_version 记的是 v4，但跑的是 v3 的 15 题（两版 Q01–Q15 相同），这里一律记 v3（spec §4.3）。
"""
import json
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.ark import parse
from app.collector import new_run, store_run
from app.config import ROOT
from app.models import Run
from app.timeutil import CST

TRIAL_DIR = ROOT / "data" / "raw" / "trial"
_NAME = re.compile(r"^trial-doubao-(api-[a-z]+)-(Q\d+)-(\d+)$")


def import_trial(session: Session, raw_dir: Path = TRIAL_DIR) -> int:
    n = 0
    for path in sorted(raw_dir.glob("trial-doubao-*.json")):
        m = _NAME.match(path.stem)
        if m is None or session.get(Run, path.stem) is not None:
            continue
        channel, qid = m[1], m[2]
        saved = json.loads(path.read_text(encoding="utf-8"))
        collected_at = datetime.fromisoformat(saved["collected_at"])
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=CST)
        run = new_run(path.stem, qid, "v3", channel, collected_at.astimezone(CST).date(), collected_at,
                      round_="trial", collector="collect/doubao_api.py")
        try:
            run.raw_path = str(path.resolve().relative_to(ROOT))
        except ValueError:
            run.raw_path = str(path)
        store_run(session, run, parse(saved["response"]))
        session.commit()
        n += 1
    return n
