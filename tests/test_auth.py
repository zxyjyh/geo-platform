import pytest

from app import auth
from app.auth import hash_password, verify_password
from app.models import User
from tests.conftest import login, make_user


@pytest.fixture
def user_inactive(session):
    return make_user(session, "bob", "pw-bob", is_active=False)


def test_password_hash_roundtrip():
    h = hash_password("s3cret")
    assert h != "s3cret" and verify_password("s3cret", h) and not verify_password("nope", h)


def test_health_is_public(client):
    assert client.get("/api/health").status_code == 200


def test_protected_requires_login(client): assert client.get("/api/auth/me").status_code == 401


def test_login_ok_then_me(client, user_alice):               # 登录 200 → /me 返回 alice
    r = login(client, "alice", "correct")
    assert r.status_code == 200 and r.json() == {"username": "alice"}
    assert client.get("/api/auth/me").json() == {"username": "alice"}


def test_logout_clears_session(authed):
    assert authed.post("/api/auth/logout").status_code == 200
    assert authed.get("/api/auth/me").status_code == 401


def test_wrong_password_401_and_rate_limit(client, user_alice):
    for _ in range(5): assert login(client, "alice", "bad").status_code == 401
    assert login(client, "alice", "correct").status_code == 429


def test_rate_limit_window_expires(client, user_alice, monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: t[0])
    for _ in range(5):
        login(client, "alice", "bad")
    assert login(client, "alice", "correct").status_code == 429
    t[0] += 15 * 60 + 1
    assert login(client, "alice", "correct").status_code == 200


def test_unknown_user_401(client):
    assert login(client, "nobody", "x").status_code == 401


def test_inactive_user_cannot_login(client, user_inactive):
    assert login(client, "bob", "pw-bob").status_code == 401


def test_deactivated_user_session_rejected(authed, session, user_alice):
    session.get(User, user_alice.id).is_active = False
    session.commit()
    assert authed.get("/api/auth/me").status_code == 401


def test_create_app_requires_secret_key(monkeypatch, session_factory):
    from app.api import create_app

    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(RuntimeError):
        create_app(session_factory)


def test_cli_create_user(tmp_path, monkeypatch, capsys):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app import cli
    from app.config import ROOT

    url = f"sqlite:///{tmp_path / 'u.db'}"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
    monkeypatch.setenv("DATABASE_URL", url)
    answers = iter(["pw1", "pw2", "pw3", "pw3"])               # 第一次两遍不一致 → 重新输入
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    cli.main(["create-user", "carol"])
    with Session(create_engine(url)) as s:
        u = s.scalars(select(User).where(User.username == "carol")).one()
        assert verify_password("pw3", u.password_hash)
