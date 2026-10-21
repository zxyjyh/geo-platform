from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url in ("sqlite://", "sqlite:///:memory:"):
        # 内存库：所有连接共用一个，测试里 TestClient 的线程也能看到同一份数据
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


SessionLocal = sessionmaker(expire_on_commit=False)


def _ensure_bound() -> None:
    if SessionLocal.kw.get("bind") is None:
        SessionLocal.configure(bind=make_engine(get_settings().database_url))


def get_session() -> Iterator[Session]:
    _ensure_bound()
    with SessionLocal() as s:
        yield s
