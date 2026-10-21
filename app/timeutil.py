"""北京时间工具。所有"哪一天"都按 Asia/Shanghai 算，和服务器时区无关。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")


def now_cst() -> datetime:
    return datetime.now(CST)


def today_cst(at: datetime | None = None) -> date:
    if at is None:
        at = now_cst()
    if at.tzinfo is None:
        # 不带时区的时间会被 astimezone 当成服务器本地时间，正是要避免的错误
        raise ValueError("today_cst 需要带时区的 datetime")
    return at.astimezone(CST).date()
