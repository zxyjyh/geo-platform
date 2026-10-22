"""登录鉴权：bcrypt 密码哈希、登录限流、current_user 依赖。"""
import os
import threading
import time
from collections import deque

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User

MAX_PASSWORD_BYTES = 72  # bcrypt 只看前 72 字节，bcrypt 5 对更长的密码直接报错
BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))  # 测试里调低，生产保持默认


def hash_password(p: str) -> str:
    raw = p.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"密码不能超过 {MAX_PASSWORD_BYTES} 字节")
    return bcrypt.hashpw(raw, bcrypt.gensalt(BCRYPT_ROUNDS)).decode("ascii")


def verify_password(p: str, h: str) -> bool:
    raw = p.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(raw, h.encode("ascii"))


# 用户不存在时也算一次哈希，响应时间不暴露用户名是否存在
DUMMY_HASH = hash_password("dummy-password-for-timing")


class LoginLimiter:
    """同一个 (username, client_ip) 在 window 秒内失败 max_failures 次后拒绝，直到最早那次失败移出窗口。
    计数在进程内存里：单实例部署够用。只有失败会写入，每次写入时顺手清掉过期记录，内存不会无限增长。"""

    def __init__(self, max_failures: int = 5, window: float = 15 * 60):
        self.max_failures = max_failures
        self.window = window
        self._fails: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def key(username: str, ip: str) -> tuple[str, str]:
        # MySQL utf8mb4_unicode_ci 不区分大小写、忽略末尾空格：Alice / alice␠ 查到同一个用户，必须共用计数
        return username.strip().casefold(), ip

    def _live(self, q: deque[float], now: float) -> deque[float]:
        while q and now - q[0] >= self.window:
            q.popleft()
        return q

    def blocked(self, key) -> bool:
        with self._lock:
            q = self._fails.get(key)
            return q is not None and len(self._live(q, time.monotonic())) >= self.max_failures

    def fail(self, key) -> None:
        with self._lock:
            now = time.monotonic()
            for k in [k for k, q in self._fails.items() if not self._live(q, now)]:
                del self._fails[k]
            self._fails.setdefault(key, deque()).append(now)

    def reset(self, key) -> None:
        with self._lock:
            self._fails.pop(key, None)

    def __len__(self) -> int:
        return len(self._fails)


def current_user(request: Request, session: Session = Depends(get_session)) -> User:
    uid = request.session.get("uid")
    user = session.get(User, uid) if uid is not None else None
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=401, detail="未登录")
    return user
