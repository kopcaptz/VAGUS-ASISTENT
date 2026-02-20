"""
JWT-аутентификация для REST API.
Использует HMAC-SHA256 (PyJWT) для подписи токенов.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any, Optional

import bcrypt

from vagus.layer0.logging import get_logger

logger = get_logger("layer3.api.auth")

SECRET_KEY = os.getenv("VAGUS_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "VAGUS_SECRET_KEY environment variable is not set. "
        "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 900  # 15 min
REFRESH_TOKEN_EXPIRE_SECONDS = 604800  # 7 days


class JWTSecretManager:
    """
    Manages active and historical JWT signing secrets with auto-rotation.
    """

    def __init__(
        self,
        *,
        initial_secret: str,
        secret_rotation_days: int = 30,
        max_old_secrets: int = 3,
    ):
        self._lock = threading.Lock()
        self._current_secret = initial_secret
        self._current_created_at = time.time()
        self._old_secrets: list[dict[str, float | str]] = []
        self.secret_rotation_days = secret_rotation_days
        self.max_old_secrets = max_old_secrets
        self._last_rotation_notice_day: Optional[int] = None

    def configure(self, *, secret_rotation_days: int, max_old_secrets: int) -> None:
        with self._lock:
            self.secret_rotation_days = max(1, int(secret_rotation_days))
            self.max_old_secrets = max(1, int(max_old_secrets))
            self._old_secrets = self._old_secrets[: self.max_old_secrets]

    def _rotation_period_seconds(self) -> int:
        return int(self.secret_rotation_days) * 24 * 60 * 60

    def _notify_if_rotation_soon(self, now_ts: float) -> None:
        seconds_left = self._rotation_period_seconds() - (now_ts - self._current_created_at)
        if seconds_left > 24 * 60 * 60:
            return

        day_marker = int(now_ts // (24 * 60 * 60))
        if self._last_rotation_notice_day == day_marker:
            return
        self._last_rotation_notice_day = day_marker
        logger.warning(
            "JWT secret rotation is due in less than 24h. rotation_days=%s",
            self.secret_rotation_days,
        )

    def _rotate_locked(self, now_ts: float) -> None:
        previous_secret = self._current_secret
        self._old_secrets.insert(
            0,
            {
                "secret": previous_secret,
                "created_at": self._current_created_at,
            },
        )
        self._old_secrets = self._old_secrets[: self.max_old_secrets]
        self._current_secret = secrets.token_urlsafe(64)
        self._current_created_at = now_ts
        self._last_rotation_notice_day = None
        logger.warning(
            "JWT secret rotated automatically. max_old_secrets=%s",
            self.max_old_secrets,
        )

    def maybe_rotate(self) -> None:
        now_ts = time.time()
        with self._lock:
            self._notify_if_rotation_soon(now_ts)
            if now_ts - self._current_created_at < self._rotation_period_seconds():
                return
            self._rotate_locked(now_ts)

    def force_rotate(self) -> None:
        with self._lock:
            self._rotate_locked(time.time())

    def get_signing_secret(self) -> str:
        self.maybe_rotate()
        with self._lock:
            return self._current_secret

    def get_verification_secrets(self) -> list[str]:
        self.maybe_rotate()
        with self._lock:
            old = [str(item["secret"]) for item in self._old_secrets]
            return [self._current_secret, *old]

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "secret_rotation_days": self.secret_rotation_days,
                "max_old_secrets": self.max_old_secrets,
                "current_created_at": self._current_created_at,
                "old_secrets_count": len(self._old_secrets),
            }

    def set_current_secret_for_testing(self, secret: str, *, created_at_ts: Optional[float] = None) -> None:
        with self._lock:
            self._current_secret = secret
            self._current_created_at = created_at_ts if created_at_ts is not None else time.time()
            self._last_rotation_notice_day = None


_jwt_secret_manager = JWTSecretManager(
    initial_secret=SECRET_KEY,
    secret_rotation_days=30,
    max_old_secrets=3,
)

def _load_users_db_from_env() -> dict[str, dict]:
    admin_username = os.getenv("VAGUS_ADMIN_USERNAME")
    admin_password_hash = os.getenv("VAGUS_ADMIN_PASSWORD_HASH")
    if not admin_username or not admin_password_hash:
        raise ValueError(
            "VAGUS_ADMIN_USERNAME and VAGUS_ADMIN_PASSWORD_HASH must be set. "
            "Generate hash with: python -c \"import bcrypt; print(bcrypt.hashpw(b'your_password', bcrypt.gensalt()).decode())\""
        )

    users_db: dict[str, dict] = {
        admin_username: {
            "username": admin_username,
            "hashed_password": admin_password_hash,
            "role": "admin",
        }
    }

    user_username = os.getenv("VAGUS_USER_USERNAME")
    user_password_hash = os.getenv("VAGUS_USER_PASSWORD_HASH")
    if bool(user_username) != bool(user_password_hash):
        raise ValueError("Set both VAGUS_USER_USERNAME and VAGUS_USER_PASSWORD_HASH, or leave both empty.")
    if user_username and user_password_hash:
        users_db[user_username] = {
            "username": user_username,
            "hashed_password": user_password_hash,
            "role": "user",
        }
    return users_db


_USERS_DB: dict[str, dict] = _load_users_db_from_env()


def _b64_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return urlsafe_b64decode(s)


def _sign(payload_b64: str, header_b64: str, secret: str) -> str:
    msg = f"{header_b64}.{payload_b64}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return _b64_encode(sig)


def configure_jwt_secret_rotation(*, secret_rotation_days: int, max_old_secrets: int) -> None:
    """Runtime-конфигурация политики ротации JWT secret."""
    _jwt_secret_manager.configure(
        secret_rotation_days=secret_rotation_days,
        max_old_secrets=max_old_secrets,
    )


def force_rotate_jwt_secret() -> None:
    """Принудительная ротация JWT secret (admin operation/tests)."""
    _jwt_secret_manager.force_rotate()


def get_jwt_rotation_state() -> dict[str, Any]:
    """Возвращает runtime состояние ротации JWT."""
    return _jwt_secret_manager.get_state()


def _set_current_jwt_secret_for_tests(secret: str, *, created_at_ts: Optional[float] = None) -> None:
    """
    Тестовый helper: устанавливает текущий JWT secret.
    """
    _jwt_secret_manager.set_current_secret_for_testing(secret, created_at_ts=created_at_ts)


def create_access_token(data: dict) -> str:
    """Создаёт JWT access token."""
    signing_secret = _jwt_secret_manager.get_signing_secret()
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        **data,
        "exp": int(time.time()) + ACCESS_TOKEN_EXPIRE_SECONDS,
        "iat": int(time.time()),
        "type": "access",
    }
    header_b64 = _b64_encode(json.dumps(header).encode())
    payload_b64 = _b64_encode(json.dumps(payload).encode())
    signature = _sign(payload_b64, header_b64, signing_secret)
    return f"{header_b64}.{payload_b64}.{signature}"


def create_refresh_token(data: dict) -> str:
    """Создаёт JWT refresh token."""
    signing_secret = _jwt_secret_manager.get_signing_secret()
    header = {"alg": ALGORITHM, "typ": "JWT"}
    payload = {
        **data,
        "exp": int(time.time()) + REFRESH_TOKEN_EXPIRE_SECONDS,
        "iat": int(time.time()),
        "type": "refresh",
    }
    header_b64 = _b64_encode(json.dumps(header).encode())
    payload_b64 = _b64_encode(json.dumps(payload).encode())
    signature = _sign(payload_b64, header_b64, signing_secret)
    return f"{header_b64}.{payload_b64}.{signature}"


def decode_token(token: str) -> Optional[dict]:
    """Декодирует и валидирует JWT. Возвращает None при ошибке."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature = parts
        signatures = [
            _sign(payload_b64, header_b64, secret)
            for secret in _jwt_secret_manager.get_verification_secrets()
        ]
        if not any(hmac.compare_digest(signature, expected_sig) for expected_sig in signatures):
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
    """Проверяет пароль против bcrypt-хеша."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Хеширует пароль с использованием bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Аутентифицирует пользователя. Возвращает dict с данными или None."""
    user = _USERS_DB.get(username)
    if user is None:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return {"sub": user["username"], "role": user["role"]}
