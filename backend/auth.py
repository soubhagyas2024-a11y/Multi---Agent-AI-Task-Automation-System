"""Password hashing, JWT sessions, role checks and a tiny in-memory rate limiter."""
from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import User

_ITER = 260_000
_bearer = HTTPBearer(auto_error=False)
_revoked: set[str] = set()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.token_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role, "jti": uuid.uuid4().hex, "exp": exp}, settings.secret_key, algorithm="HS256")


def revoke_token(token: str) -> None:
    try:
        _revoked.add(jwt.decode(token, settings.secret_key, algorithms=["HS256"])["jti"])
    except jwt.PyJWTError:
        pass


def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)) -> User:
    err = HTTPException(401, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if not creds:
        raise err
    try:
        data = jwt.decode(creds.credentials, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise err
    if data.get("jti") in _revoked:
        raise err
    user = db.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise err
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int | None = None, window: int = 60) -> None:
        limit = limit or settings.rate_limit_per_minute
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(429, "Too many requests - please slow down")
            q.append(now)


limiter = RateLimiter()


def rate_limited(user: User = Depends(get_current_user)) -> User:
    limiter.check(f"user:{user.id}")
    return user


def ip_limit(request: Request, limit: int = 10) -> None:
    limiter.check(f"ip:{request.client.host if request.client else 'unknown'}:{request.url.path}", limit=limit)
