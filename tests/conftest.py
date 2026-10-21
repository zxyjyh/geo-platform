import os

import pytest
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET_KEY", "test-secret")

from app.db import Base, make_engine  # noqa: E402


@pytest.fixture
def session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s
