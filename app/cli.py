"""用法：uv run python -m app.cli <命令>
  import-trial                                  导入 data/raw/trial 的试跑数据（round=trial，不进看板）
  run-daily [--date YYYY-MM-DD] [--channel …]   立即跑一次每日采集（默认北京时间今天、设置里的渠道）
"""
import argparse
import sys
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import make_engine
from app.seed import seed_all


def _session() -> Session:
    return sessionmaker(make_engine(get_settings().database_url), expire_on_commit=False)()


def cmd_import_trial(args) -> None:
    from app.importer import import_trial

    with _session() as s:
        seed_all(s)
        print(f"导入 {import_trial(s)} 条 trial run")


def cmd_run_daily(args) -> None:
    from app.ark import HttpArkClient
    from app.collector import run_daily, setting
    from app.timeutil import today_cst

    cfg = get_settings()
    if not cfg.ark_api_key:
        sys.exit("缺少环境变量 ARK_API_KEY")
    with _session() as s:
        seed_all(s)
        d = date.fromisoformat(args.date) if args.date else today_cst()
        channel = args.channel or setting(s, "api_channel", "api-custom")
        r = run_daily(s, HttpArkClient(cfg.ark_api_key), d, channel, cfg.raw_dir)
        print(f"{d} {channel}：成功 {r.n_ok}，失败 {r.n_failed} {r.failed_qids}，跳过 {r.n_skipped}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import-trial").set_defaults(func=cmd_import_trial)
    p = sub.add_parser("run-daily")
    p.add_argument("--date")
    p.add_argument("--channel", choices=["api-custom", "api-plugin"])
    p.set_defaults(func=cmd_run_daily)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
