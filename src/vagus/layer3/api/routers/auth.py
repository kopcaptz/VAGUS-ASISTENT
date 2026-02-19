"""
Роутер аутентификации: получение и обновление JWT-токенов.
"""

from fastapi import APIRouter, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends

from ..auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from ..models import TokenRequest, TokenResponse

router = APIRouter(tags=["Auth"])


@router.post("/token", response_model=TokenResponse)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Authenticates user and returns access + refresh tokens."""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = {"sub": user["username"], "roles": user.get("roles", ["user"])}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(request: TokenRequest):
    """Uses a refresh token to issue a new access token."""
    payload = decode_refresh_token(request.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    token_data = {"sub": payload["sub"], "roles": payload.get("roles", ["user"])}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )
