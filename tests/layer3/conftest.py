"""
Фикстуры для тестов Layer 3.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from vagus.layer3.api.auth import create_access_token, create_refresh_token
from vagus.layer3.api.main import create_app
from vagus.layer3.api.routers.tasks import task_store


def _make_mock_orchestrator():
    """Создаёт мок-оркестратор с агентами."""
    orchestrator = AsyncMock()

    agent1 = MagicMock()
    agent1.name = "researcher"
    agent1.description = "Агент для поиска информации"
    agent1.can_handle.return_value = True

    agent2 = MagicMock()
    agent2.name = "coder"
    agent2.description = "Агент для генерации кода"
    agent2.can_handle.return_value = True

    agent3 = MagicMock()
    agent3.name = "analyst"
    agent3.description = "Агент для анализа данных"
    agent3.can_handle.return_value = True

    orchestrator.agents = [agent1, agent2, agent3]
    orchestrator.execute_task = AsyncMock(
        return_value={"content": "Test result", "metadata": {"agent": "researcher"}}
    )
    return orchestrator


def _make_mock_llm_router():
    """Создаёт мок LLM Router."""
    router = MagicMock()
    router.get_stats.return_value = {
        "requests": 42,
        "total_cost": 0.05,
        "cache": {"hit_rate_percent": 75.0},
    }
    return router


@pytest.fixture
def app():
    """FastAPI app без lifespan (для тестов)."""
    from fastapi import FastAPI
    from vagus.layer3.api.middleware import RateLimitMiddleware
    from vagus.layer3.api.routers import agents_router, auth_router, status_router, tasks_router

    test_app = FastAPI(title="Vagus Asistent API", version="1.0.0")
    test_app.add_middleware(RateLimitMiddleware, max_requests=1000, window_seconds=60)
    test_app.include_router(auth_router, prefix="/api/v1")
    test_app.include_router(tasks_router, prefix="/api/v1")
    test_app.include_router(agents_router, prefix="/api/v1")
    test_app.include_router(status_router, prefix="/api/v1")

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    test_app.state.orchestrator = _make_mock_orchestrator()
    test_app.state.llm_router = _make_mock_llm_router()
    test_app.state.start_time = time.monotonic()
    return test_app


@pytest.fixture
def client(app):
    """TestClient с мок-зависимостями."""
    task_store.clear()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    task_store.clear()


@pytest.fixture
def admin_token():
    """JWT access token для admin."""
    return create_access_token({"sub": "admin", "role": "admin"})


@pytest.fixture
def user_token():
    """JWT access token для обычного пользователя."""
    return create_access_token({"sub": "user", "role": "user"})


@pytest.fixture
def admin_headers(admin_token):
    """HTTP-заголовки с JWT admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def user_headers(user_token):
    """HTTP-заголовки с JWT user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def refresh_token_admin():
    """JWT refresh token для admin."""
    return create_refresh_token({"sub": "admin", "role": "admin"})
