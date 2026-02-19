"""
FastAPI dependencies — внедрение зависимостей.
Провайдеры сервисов для роутеров (LLM Router, Config и т.д.).
"""

from typing import Any, Dict

from fastapi import Request

from vagus.layer2.orchestrator import TaskOrchestrator


def get_orchestrator(request: Request) -> TaskOrchestrator:
    """Возвращает TaskOrchestrator из app.state."""
    return request.app.state.orchestrator


def get_task_store(request: Request) -> Dict[str, Any]:
    """Возвращает хранилище задач из app.state."""
    return request.app.state.task_store


def get_current_user(request: Request) -> Any:
    """
    Возвращает текущего пользователя.
    Пока без аутентификации — всегда None (все запросы разрешены).
    """
    return None
