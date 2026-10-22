"""路由共用：设置读取、日期参数、序列化。"""
from dataclasses import asdict
from datetime import date, timedelta
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collector import ROUND, setting
from app.models import Run
from app.timeutil import today_cst

MAX_SPAN_DAYS = 366
# 被测的大模型（runs.platform）。接入千问后在这里加 "qianwen"，前端下拉框同时放开
ModelPlatform = Literal["doubao"]


def alias_version(session: Session) -> int:
    return int(setting(session, "alias_version", "1"))


def api_channel(session: Session, channel: str | None = None) -> str:
    return channel or setting(session, "api_channel", "api-custom")


def latest_date(session: Session, channel: str, platform: str = "doubao") -> date | None:
    return session.scalar(select(func.max(Run.collect_date))
                          .where(Run.round == ROUND, Run.platform == platform, Run.channel == channel,
                                 Run.status == "valid"))


def first_date(session: Session, channel: str, platform: str = "doubao") -> date | None:
    return session.scalar(select(func.min(Run.collect_date))
                          .where(Run.round == ROUND, Run.platform == platform, Run.channel == channel,
                                 Run.status == "valid"))


def date_range(start: date | None, end: date | None, default_days: int = 30) -> tuple[date, date]:
    end = end or today_cst()
    start = start or end - timedelta(days=default_days - 1)
    if start > end:
        raise HTTPException(422, "start 不能晚于 end")
    if (end - start).days >= MAX_SPAN_DAYS:
        raise HTTPException(422, f"日期范围不能超过 {MAX_SPAN_DAYS} 天")
    return start, end


def to_json(obj):
    """dataclass → dict（Ratio 变成 {num, den}；日期由 FastAPI 序列化成 ISO）。"""
    return asdict(obj)
