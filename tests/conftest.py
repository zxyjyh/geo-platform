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


@pytest.fixture
def trial_custom_texts():
    """trial 里 api-custom 渠道 10 道不带品牌名的题的回答原文。"""
    import csv
    import json

    from app.ark import parse
    from app.config import ROOT

    with open(ROOT / "data" / "questions" / "questions-v3-15.csv", encoding="utf-8-sig") as f:
        unbranded = [r["qid"] for r in csv.DictReader(f) if r["branded"] == "N"]
    texts = []
    for qid in unbranded:
        path = ROOT / "data" / "raw" / "trial" / f"trial-doubao-api-custom-{qid}-1.json"
        texts.append(parse(json.loads(path.read_text(encoding="utf-8"))["response"]).text)
    assert len(texts) == 10
    return texts


@pytest.fixture
def platforms(session):
    from sqlalchemy import select

    from app.models import Platform
    from app.seed import seed_all

    seed_all(session)
    return list(session.scalars(select(Platform)))


@pytest.fixture
def app(session_factory):
    from app.api import create_app

    return create_app(session_factory)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def make_user(session, username, password, is_active=True):
    from app.auth import hash_password
    from app.models import User
    from app.timeutil import now_cst

    u = User(username=username, password_hash=hash_password(password), is_active=is_active, created_at=now_cst())
    session.add(u)
    session.commit()
    return u


@pytest.fixture
def user_alice(session):
    return make_user(session, "alice", "correct")


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture
def authed(client, user_alice):
    assert login(client, "alice", "correct").status_code == 200
    return client
