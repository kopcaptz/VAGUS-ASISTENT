"""
JWT-аутентификация для REST API.
Использует HMAC-SHA256 (PyJWT) для подписи токенов.
"""

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional


SECRET_KEY = os.getenv("VAGUS_SECRET_KEY", "vagus-dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 900  # 15 min
REFRESH_TOKEN_EXPIRE_SECONDS = 604800  # 7 days

_USERS_DB: dict[str, dict] = {
    "admin": {
        "username": "admin",
        "hashed_password": hashlib.sha256(b"admin").hexdigest(),
        "role": "admin",
    },
    "user": {
        "username": "user",
        "hashed_password": hashlib.sha256(b"user").hexdigest(),
        "role": "user",
    },
}


def _b64_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return urlsafe_b64decode(s)


def _sign(payload_b64: str, header_b64: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return _b64_encode(sig)


def create_access_token(data: dict) -> str:
    """Создаёт JWT access token."""
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        **data,
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS,
        "iat": int(time.time()),
        "type": "access",
    }
    header_b64 = _b64_encode(json.dumps(header).encode())
    payload_b64 = _b64_encode(json.dumps(payload).encode())
    signature = _sign(payload_b64, header_b64)
    return f"{header_b64}.{payload_b64}.{signature}"


def create_refresh_token(data: dict) -> str:
    """Создаёт JWT refresh token."""
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        **data,
        "exp": int(time.time()) + REFRESH_TOKEN_EXPIRE_SECONDS,
        "iat": int(time.time()),
        "type": "refresh",
    }
    header_b64 = _b64_encode(json.dumps(header).encode())
    payload_b64 = _b64_encode(json.dumps(payload).encode())
    signature = _sign(payload_b64, header_b64)
    return f"{header_b64}.{payload_b64}.{signature}"


def decode_token(token: str) -> Optional[dict]:
    """Декодирует и валидирует JWT. Возвращает None при ошибке."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature = parts
        expected_sig = _sign(payload_b64, header_b64)
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(_b64_decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def decode_access_token(token: str) -> Optional[dict]:
    """Декодирует access token. Возвращает None если невалиден или не access."""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        return None
    return payload


def decode_refresh_token(token: str) -> Optional[dict]:
    """Декодирует refresh token."""
    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        return None
    return payload


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Сравнивает пароль с хэшем (SHA-256)."""
    return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password


def get_password_hash(password: str) -> str:
    """Хэширует пароль (SHA-256)."""
    return hashlib.sha256(password.encode()).hexdigest()


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Аутентифицирует пользователя. Возвращает dict с данными или None."""
    user = _USERS_DB.get(username)
    if user is None:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return {"sub": user["username"], "role": user["role"]}
