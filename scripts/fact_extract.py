"""批量事实抽取（spec §4.11）。

用法：python -m scripts.fact_extract [--date YYYY-MM-DD] [--channel api-custom|api-plugin] [--reextract]
"""
import argparse
import os
import sys
from datetime import date

from sqlalchemy import select, delete
from sqlalchemy.orm import sessionmaker

from app.config import get_settings, ROOT
from app.db import make_engine
from app.models import FactClaim, FactItem, Run, Coding, Setting
from app.collector import ROUND, setting
from app.factcheck import extract_and_store
from app.timeutil import today_cst


def main():
    parser = argparse.ArgumentParser(description="批量事实抽取")
    parser.add_argument("--date", type=str, default=None, help="日期，默认今天")
    parser.add_argument("--channel", type=str, default=None, help="渠道，默认设置里的")
    parser.add_argument("--reextract", action="store_true", help="清空旧抽取结果再重抽")
    args = parser.parse_args()

    cfg = get_settings()
    if not cfg.ark_api_key:
        sys.exit("缺少环境变量 ARK_API_KEY")

    engine = make_engine(cfg.database_url)
    Session = sessionmaker(engine, expire_on_commit=False)

    target_date = date.fromisoformat(args.date) if args.date else today_cst()

    with Session() as session:
        channel = args.channel or setting(session, "api_channel", "api-custom")
        version = int(setting(session, "fact_extract_version", "1"))

        # 获取当前事实清单
        fact_version = int(setting(session, "fact_item_version", "0"))
        items = [{"code": i.code, "subject": i.subject, "correct_claim": i.correct_claim}
                 for i in session.scalars(select(FactItem).where(FactItem.version == fact_version))]

        # 获取目标 run
        runs = list(session.scalars(
            select(Run).join(Coding, (Coding.run_id == Run.run_id))
            .where(Run.collect_date == target_date, Run.channel == channel,
                   Run.round == ROUND, Run.status == "valid", Coding.mention_aomi.is_(True))
            .order_by(Run.qid, Run.rep)))

        if args.reextract:
            run_ids = [r.run_id for r in runs]
            if run_ids:
                session.execute(delete(FactClaim).where(
                    FactClaim.run_id.in_(run_ids), FactClaim.extract_version == version))
                session.commit()

        processed = 0
        new_claims = 0
        for run in runs:
            n = extract_and_store(session, run, items, cfg.ark_api_key, version)
            session.commit()
            processed += 1
            new_claims += n
            print(f"[{processed}/{len(runs)}] {run.run_id}: +{n} claims")

        print(f"\n完成：处理 {processed} 条，新增 {new_claims} 条 claim")


if __name__ == "__main__":
    main()
