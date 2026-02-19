"""
FastAPI зависимости (Depends).
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from .auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_orchestrator(request: Request):
    """Зависимость: экземпляр TaskOrchestrator из app.state."""
    return request.app.state.orchestrator


def get_llm_router(request: Request):
    """Зависимость: экземпляр LLMRouter из app.state."""
    return request.app.state.llm_router


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Зависимость: декодирует JWT и возвращает данные пользователя."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    return payload


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Зависимость: проверяет роль admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
