from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text,
                        TypeDecorator, UniqueConstraint)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.timeutil import CST

UTF8MB4 = {"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"}
LongText = Text().with_variant(mysql.MEDIUMTEXT(), "mysql")


def BinString(n: int):
    """区分大小写的字符串列：表级 utf8mb4_unicode_ci 不区分大小写，别名（Aomi/aomi）和 URL 路径都需要区分。"""
    return String(n).with_variant(mysql.VARCHAR(n, collation="utf8mb4_bin"), "mysql")


class CSTDateTime(TypeDecorator):
    """库里存北京时间的墙上时间（MySQL DATETIME / SQLite 都不保存时区），读出来补回 Asia/Shanghai。"""
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("写库的时间必须带时区")
        return value.astimezone(CST).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=CST)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = UTF8MB4
    qid: Mapped[str] = mapped_column(String(16), primary_key=True)
    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    text: Mapped[str] = mapped_column(String(512))
    branded: Mapped[bool] = mapped_column(Boolean)
    scene: Mapped[str] = mapped_column(String(128), default="")
    intent: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = UTF8MB4
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    round: Mapped[str] = mapped_column(String(32), index=True)
    qid: Mapped[str] = mapped_column(String(16), index=True)
    question_version: Mapped[str] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(32), default="doubao")
    channel: Mapped[str] = mapped_column(String(32), index=True)
    channel_detail: Mapped[str] = mapped_column(String(256), default="")
    mode: Mapped[str] = mapped_column(String(32), default="")
    collected_at: Mapped[datetime] = mapped_column(CSTDateTime())
    collect_date: Mapped[date] = mapped_column(Date, index=True)
    collector: Mapped[str] = mapped_column(String(64), default="")
    account_ref: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(64), default="")
    new_session: Mapped[bool] = mapped_column(Boolean, default=True)
    answer_text: Mapped[str] = mapped_column(LongText, default="")
    raw_path: Mapped[str] = mapped_column(String(512), default="")
    sources_visible: Mapped[bool] = mapped_column(Boolean, default=False)
    sources_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16))  # valid / void / failed
    error: Mapped[str | None] = mapped_column(LongText, nullable=True)
    search_queries: Mapped[str] = mapped_column(Text, default="")
    search_rounds: Mapped[int] = mapped_column(Integer, default=0)
    billed_searches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = UTF8MB4
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(Text)
    url_norm: Mapped[str] = mapped_column(BinString(768), index=True)
    domain: Mapped[str] = mapped_column(String(255), default="")
    site_name: Mapped[str] = mapped_column(String(255), default="")
    publish_time_raw: Mapped[str] = mapped_column(String(64), default="")
    publish_time: Mapped[datetime | None] = mapped_column(CSTDateTime(), nullable=True)
    platform_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_owned: Mapped[bool] = mapped_column(Boolean, default=False)


class Coding(Base):
    __tablename__ = "codings"
    __table_args__ = UTF8MB4
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id", ondelete="CASCADE"), primary_key=True)
    alias_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    mention_aomi: Mapped[bool] = mapped_column(Boolean)
    mention_mfood: Mapped[bool] = mapped_column(Boolean)
    mention_shanfeng: Mapped[bool] = mapped_column(Boolean)
    order_aomi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_mfood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    order_shanfeng: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (UniqueConstraint("version", "entity", "alias"), UTF8MB4)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    entity: Mapped[str] = mapped_column(String(32))
    alias: Mapped[str] = mapped_column(BinString(64))


class Platform(Base):
    __tablename__ = "platforms"
    __table_args__ = UTF8MB4
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    domain_suffix: Mapped[str] = mapped_column(String(255))
    publishable: Mapped[bool] = mapped_column(Boolean, default=True)


class OwnedPrefix(Base):
    __tablename__ = "owned_prefixes"
    __table_args__ = UTF8MB4
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    url_prefix: Mapped[str] = mapped_column(String(512))


class SourceTag(Base):
    __tablename__ = "source_tags"
    __table_args__ = UTF8MB4
    url_norm: Mapped[str] = mapped_column(BinString(768), primary_key=True)
    tag: Mapped[str] = mapped_column(String(32))  # external_geo
    note: Mapped[str] = mapped_column(Text, default="")


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_job_date", "job", "run_date"), UTF8MB4)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(32))  # daily_collect
    run_date: Mapped[date] = mapped_column(Date)
    channel: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))  # requested / running / done / failed
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(CSTDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(CSTDateTime(), nullable=True)
    n_ok: Mapped[int] = mapped_column(Integer, default=0)
    n_failed: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")


class User(Base):
    __tablename__ = "users"
    __table_args__ = UTF8MB4
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(CSTDateTime())


class Setting(Base):
    __tablename__ = "settings"
    __table_args__ = UTF8MB4
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
