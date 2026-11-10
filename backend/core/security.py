"""Password hashing (scrypt, stdlib) and JWT access tokens (HS256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt

from .config import get_settings

_N, _R, _P = 2**14, 8, 1  # scrypt cost parameters (~16 MB, ~50 ms)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p),
                                dklen=len(base64.b64decode(hash_b64)))
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> tuple[str, int]:
    s = get_settings()
    expires = datetime.now(UTC) + timedelta(minutes=s.access_token_expire_minutes)
    token = jwt.encode({"sub": str(user_id), "exp": expires, "type": "access"}, s.secret_key, algorithm="HS256")
    return token, s.access_token_expire_minutes * 60


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None
