"""
Роутер аутентификации: /auth/token, /auth/refresh.
"""

from fastapi import APIRouter, HTTPException, status

from ..auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from ..models import RefreshTokenRequest, TokenRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/token", response_model=TokenResponse)
async def login(request: TokenRequest):
    """Аутентификация по логину/паролю. Возвращает access + refresh токены."""
    user_data = authenticate_user(request.username, request.password)
    if user_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user_data),
        refresh_token=create_refresh_token(user_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshTokenRequest):
    """Обновление access_token с помощью refresh_token."""
    payload = decode_refresh_token(request.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    user_data = {"sub": payload["sub"], "role": payload.get("role", "user")}
    return TokenResponse(
        access_token=create_access_token(user_data),
        refresh_token=create_refresh_token(user_data),
    )
