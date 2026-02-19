"""
FastAPI dependencies — внедрение зависимостей.
Провайдеры сервисов для роутеров (LLM Router, Config и т.д.).
"""

from typing import Any, Dict

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from vagus.layer2.orchestrator import TaskOrchestrator

from .auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_orchestrator(request: Request) -> TaskOrchestrator:
    """Возвращает TaskOrchestrator из app.state."""
    return request.app.state.orchestrator


def get_task_store(request: Request) -> Dict[str, Any]:
    """Возвращает хранилище задач из app.state."""
    return request.app.state.task_store


def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Возвращает текущего пользователя из JWT.
    Вызывает 401 при невалидном или отсутствующем токене.
    """
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"sub": username, "username": username}
