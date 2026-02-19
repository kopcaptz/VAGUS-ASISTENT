"""Authentication module — JWT-based auth for Vagus API."""

from .auth import (
    AuthService,
    TokenPair,
    get_current_user,
    ALGORITHM,
)

__all__ = ["AuthService", "TokenPair", "get_current_user", "ALGORITHM"]
