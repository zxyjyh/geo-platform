from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DUMMY_HASH, current_user, verify_password
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/auth")


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, session: Session = Depends(get_session)):
    limiter = request.app.state.login_limiter
    key = (body.username, request.client.host if request.client else "")
    if limiter.blocked(key):
        raise HTTPException(status_code=429, detail="失败次数过多，请 15 分钟后再试")
    user = session.scalars(select(User).where(User.username == body.username)).first()
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not (ok and user is not None and user.is_active):
        limiter.fail(key)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    limiter.reset(key)
    request.session.clear()
    request.session["uid"] = user.id
    return {"username": user.username}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"username": user.username}
