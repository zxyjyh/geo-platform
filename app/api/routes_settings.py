from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ark import CHANNELS
from app.auth import current_user, hash_password
from app.coding import ENTITIES, recode_all
from app.collector import setting
from app.db import get_session
from app.models import Alias, JobRun, OwnedPrefix, Platform, Setting, Source, User
from app.timeutil import now_cst, today_cst
from app.urls import is_owned, platform_for

router = APIRouter(prefix="/settings", dependencies=[Depends(current_user)])


def _int(v: str) -> bool:
    return v.isdigit() and int(v) > 0


def _ratio(v: str) -> bool:
    try:
        return 0 < float(v) <= 1
    except ValueError:
        return False


def _price(v: str) -> bool:
    if v == "":
        return True
    try:
        return float(v) >= 0
    except ValueError:
        return False


# 页面上能改的设置和校验规则。alias_version / question_version 不在这里：前者只能通过改别名表升版本
EDITABLE = {
    "api_channel": lambda v: v in CHANNELS,
    "weak_recent_n": _int,
    "weak_mention_ratio": _ratio,
    "platform_window_days": _int,
    "price_per_search_yuan": _price,
    "price_input_per_1k_yuan": _price,
    "price_output_per_1k_yuan": _price,
}


@router.get("")
def get_settings(session: Session = Depends(get_session)):
    return {s.key: s.value for s in session.scalars(select(Setting).order_by(Setting.key))}


@router.put("")
def put_settings(body: dict[str, str], session: Session = Depends(get_session)):
    bad = [k for k in body if k not in EDITABLE]
    if bad:
        raise HTTPException(422, f"不允许修改：{bad}")
    invalid = [k for k, v in body.items() if not EDITABLE[k](v.strip())]
    if invalid:
        raise HTTPException(422, f"取值不合法：{invalid}")
    for k, v in body.items():
        row = session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v.strip()))
        else:
            row.value = v.strip()
    session.commit()
    return get_settings(session)


def _aliases(session: Session, version: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {e: [] for e in ENTITIES}
    for a in session.scalars(select(Alias).where(Alias.version == version).order_by(Alias.id)):
        out.setdefault(a.entity, []).append(a.alias)
    return out


@router.get("/aliases")
def get_aliases(session: Session = Depends(get_session)):
    return _aliases(session, int(setting(session, "alias_version", "1")))


@router.put("/aliases")
def put_aliases(body: dict[str, list[str]], session: Session = Depends(get_session)):
    """生成新版本的完整别名表 → 全部 valid run 用新版本重算 → settings.alias_version 指向新版本。"""
    if set(body) != set(ENTITIES):
        raise HTTPException(422, f"必须同时给出三家：{list(ENTITIES)}")
    cleaned = {}
    for e in ENTITIES:
        names = list(dict.fromkeys(a.strip() for a in body[e]))
        if not names or any(not a or len(a) > 64 for a in names):
            raise HTTPException(422, f"{e} 的别名不能为空、每个不超过 64 字")
        cleaned[e] = names
    new_version = (session.scalar(select(func.max(Alias.version))) or 0) + 1
    session.add_all(Alias(version=new_version, entity=e, alias=a) for e, names in cleaned.items() for a in names)
    session.flush()
    n = recode_all(session, new_version)
    session.get(Setting, "alias_version").value = str(new_version)
    session.commit()
    return {"version": new_version, "recoded": n, "aliases": cleaned}


class PlatformBody(BaseModel):
    key: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=64)
    domain_suffix: str = Field(min_length=1, max_length=255)
    publishable: bool = True


def _recompute_sources(session: Session, platforms: bool = False, owned: bool = False) -> None:
    ps = list(session.scalars(select(Platform)))
    prefixes = list(session.scalars(select(OwnedPrefix)))
    for s in session.scalars(select(Source)):
        if platforms:
            s.platform_key = platform_for(s.domain, ps)
        if owned:
            s.is_owned = is_owned(s.url, prefixes)


def _platform_json(p: Platform):
    return {"key": p.key, "name": p.name, "domain_suffix": p.domain_suffix, "publishable": p.publishable}


@router.get("/platforms")
def get_platforms(session: Session = Depends(get_session)):
    return [_platform_json(p) for p in session.scalars(select(Platform).order_by(Platform.key))]


@router.put("/platforms")
def put_platforms(body: list[PlatformBody], session: Session = Depends(get_session)):
    """整表替换（不在列表里的平台删除），然后重算所有信源的 platform_key。"""
    keys = [p.key for p in body]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, "平台 key 重复")
    for p in session.scalars(select(Platform)):
        if p.key not in keys:
            session.delete(p)
    for b in body:
        row = session.get(Platform, b.key)
        if row is None:
            session.add(Platform(**b.model_dump()))
        else:
            row.name, row.domain_suffix, row.publishable = b.name, b.domain_suffix.strip().lower(), b.publishable
    session.flush()
    _recompute_sources(session, platforms=True)
    session.commit()
    return get_platforms(session)


class PrefixBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url_prefix: str = Field(min_length=1, max_length=512)


@router.get("/owned-prefixes")
def get_prefixes(session: Session = Depends(get_session)):
    return [{"id": p.id, "name": p.name, "url_prefix": p.url_prefix}
            for p in session.scalars(select(OwnedPrefix).order_by(OwnedPrefix.id))]


@router.post("/owned-prefixes")
def add_prefix(body: PrefixBody, session: Session = Depends(get_session)):
    p = OwnedPrefix(name=body.name, url_prefix=body.url_prefix.strip())
    session.add(p)
    session.flush()
    _recompute_sources(session, owned=True)
    session.commit()
    return {"id": p.id, "name": p.name, "url_prefix": p.url_prefix}


@router.delete("/owned-prefixes/{pid}")
def delete_prefix(pid: int, session: Session = Depends(get_session)):
    p = session.get(OwnedPrefix, pid)
    if p is None:
        raise HTTPException(404, "没有这个前缀")
    session.delete(p)
    session.flush()
    _recompute_sources(session, owned=True)
    session.commit()
    return {"deleted": pid}


def _job_json(j: JobRun):
    return {"id": j.id, "job": j.job, "run_date": j.run_date, "channel": j.channel, "status": j.status,
            "requested_by": j.requested_by, "started_at": j.started_at, "finished_at": j.finished_at,
            "n_ok": j.n_ok, "n_failed": j.n_failed, "message": j.message}


@router.get("/jobs")
def list_jobs(limit: int = Query(30, ge=1, le=200), session: Session = Depends(get_session)):
    return [_job_json(j) for j in session.scalars(select(JobRun).order_by(JobRun.id.desc()).limit(limit))]


class RerunBody(BaseModel):
    date: date


@router.post("/jobs/rerun")
def rerun(body: RerunBody, user: User = Depends(current_user), session: Session = Depends(get_session)):
    """只登记请求，由 worker 执行（worker 串行执行，不会和定时任务重叠）。"""
    if body.date > today_cst():
        raise HTTPException(422, "不能补跑未来的日期")
    j = JobRun(job="daily_collect", run_date=body.date, channel=setting(session, "api_channel", "api-custom"),
               status="requested", requested_by=user.username, n_ok=0, n_failed=0, message="")
    session.add(j)
    session.commit()
    return _job_json(j)


class NewUser(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)


class UserPatch(BaseModel):
    is_active: bool


def _user_json(u: User):
    return {"id": u.id, "username": u.username, "is_active": u.is_active, "created_at": u.created_at}


@router.get("/users")
def list_users(session: Session = Depends(get_session)):
    return [_user_json(u) for u in session.scalars(select(User).order_by(User.id))]


@router.post("/users")
def create_user(body: NewUser, session: Session = Depends(get_session)):
    name = body.username.strip()
    if session.scalars(select(User).where(User.username == name)).first() is not None:
        raise HTTPException(409, "用户名已存在")
    try:
        ph = hash_password(body.password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    u = User(username=name, password_hash=ph, is_active=True, created_at=now_cst())
    session.add(u)
    session.commit()
    return _user_json(u)


@router.patch("/users/{uid}")
def patch_user(uid: int, body: UserPatch, user: User = Depends(current_user),
               session: Session = Depends(get_session)):
    u = session.get(User, uid)
    if u is None:
        raise HTTPException(404, "没有这个用户")
    if u.id == user.id and not body.is_active:
        raise HTTPException(422, "不能停用自己的账号")
    u.is_active = body.is_active
    session.commit()
    return _user_json(u)
