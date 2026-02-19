"""
Роутер аутентификации.
Эндпоинты: логин, logout, refresh токена, регистрация.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)

router = APIRouter(prefix="/auth")


class TokenResponse(BaseModel):
    """Ответ с токенами."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Запрос на обновление access token."""

    refresh_token: str


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Получение access и refresh токенов по username/password."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token({"sub": user["username"]})
    refresh_token = create_refresh_token({"sub": user["username"]})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    body: RefreshRequest,
):
    """Обновление access token по refresh token."""
    payload = decode_refresh_token(body.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    access_token = create_access_token({"sub": username})
    refresh_token = create_refresh_token({"sub": username})
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )
