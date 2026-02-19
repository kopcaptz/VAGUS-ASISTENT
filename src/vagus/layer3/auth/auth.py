"""
JWT authentication for Vagus API.
Handles user login, token creation, and token refresh.
"""

import hashlib
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = 3600
REFRESH_TOKEN_EXPIRE = 86400 * 7

_security = HTTPBearer()


def _get_secret() -> str:
    return os.environ.get("VAGUS_JWT_SECRET", "vagus-dev-secret-key")


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthService:
    """Manages user credentials and JWT lifecycle."""

    def __init__(self) -> None:
        self._users: dict[str, str] = {}

    def register_user(self, username: str, password: str) -> None:
        self._users[username] = self._hash(password)

    def authenticate(self, username: str, password: str) -> Optional[TokenPair]:
        stored = self._users.get(username)
        if stored is None or stored != self._hash(password):
            return None
        return self._issue_tokens(username)

    def refresh(self, refresh_token: str) -> Optional[TokenPair]:
        payload = self._decode(refresh_token)
        if payload is None or payload.get("type") != "refresh":
            return None
        username = payload.get("sub")
        if username is None or username not in self._users:
            return None
        return self._issue_tokens(username)

    def _issue_tokens(self, username: str) -> TokenPair:
        now = time.time()
        access = jwt.encode(
            {"sub": username, "type": "access", "iat": now, "exp": now + ACCESS_TOKEN_EXPIRE},
            _get_secret(),
            algorithm=ALGORITHM,
        )
        refresh = jwt.encode(
            {"sub": username, "type": "refresh", "iat": now, "exp": now + REFRESH_TOKEN_EXPIRE},
            _get_secret(),
            algorithm=ALGORITHM,
        )
        return TokenPair(access_token=access, refresh_token=refresh)

    @staticmethod
    def _decode(token: str) -> Optional[dict[str, Any]]:
        try:
            return jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            return None

    @staticmethod
    def _hash(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """FastAPI dependency — extracts username from JWT or raises 401."""
    payload = AuthService._decode(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return username
