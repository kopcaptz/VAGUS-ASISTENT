"""
Аутентификация и авторизация API.
Проверка токенов, JWT, API keys, права доступа.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _get_secret_key() -> str:
    """Загружает SECRET_KEY из переменной окружения."""
    key = os.getenv("VAGUS_SECRET_KEY")
    if not key:
        raise ValueError("VAGUS_SECRET_KEY environment variable is required")
    return key


def create_access_token(data: dict) -> str:
    """Создаёт access token со сроком 15 минут."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Создаёт refresh token со сроком 7 дней."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Декодирует и валидирует access token. Возвращает payload или None."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[Dict[str, Any]]:
    """Декодирует и валидирует refresh token. Возвращает payload или None."""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        return payload
    except JWTError:
        return None


def verify_password(plain: str, hashed: str) -> bool:
    """Проверяет пароль против хэша."""
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    """Возвращает bcrypt хэш пароля."""
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Проверяет учётные данные пользователя.
    Пользователи задаются через VAGUS_ADMIN_USER и VAGUS_ADMIN_PASSWORD (или VAGUS_ADMIN_PASSWORD_HASH).
    """
    admin_user = os.getenv("VAGUS_ADMIN_USER")
    admin_password = os.getenv("VAGUS_ADMIN_PASSWORD")
    admin_password_hash = os.getenv("VAGUS_ADMIN_PASSWORD_HASH")

    if not admin_user:
        return None

    if username != admin_user:
        return None

    if admin_password_hash:
        if not verify_password(password, admin_password_hash):
            return None
    elif admin_password:
        if password != admin_password:
            return None
    else:
        return None

    return {"sub": username, "username": username}
