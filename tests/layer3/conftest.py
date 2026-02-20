"""
Фикстуры для тестов Layer 3.
"""

import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from vagus.logging import StructuredLoggingMiddleware, configure_structured_logging
from vagus.layer3.api.auth import create_access_token, create_refresh_token
from vagus.layer3.api.audit.audit_trail import AuditTrail
from vagus.layer3.api.health import HealthThresholds, health_router
from vagus.layer3.api.metrics import HTTPMetricsMiddleware, metrics_router
from vagus.layer3.api.routers.tasks import task_store
from vagus.layer3.api.websocket_security import WebSocketAuditStorage, WebSocketRuntimeSettings
from vagus.layer2.dead_letter_queue import DeadLetterQueueStorage
from vagus.monitoring.error_analytics import ErrorAnalyticsStorage


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
def app(tmp_path):
    """FastAPI app без lifespan (для тестов)."""
    from fastapi import FastAPI
    from vagus.layer3.api.middleware import RateLimitMiddleware
    from vagus.layer3.api.routers import (
        admin_router,
        agents_router,
        auth_router,
        keys_router,
        plugins_router,
        status_router,
        tasks_router,
    )

    configure_structured_logging(force=True)
    test_app = FastAPI(title="Vagus Asistent API", version="1.0.0")
    test_app.add_middleware(RateLimitMiddleware, max_requests=1000, window_seconds=60)
    test_app.add_middleware(HTTPMetricsMiddleware)
    test_app.add_middleware(StructuredLoggingMiddleware, component="api-test")
    test_app.include_router(auth_router, prefix="/api/v1")
    test_app.include_router(tasks_router, prefix="/api/v1")
    test_app.include_router(agents_router, prefix="/api/v1")
    test_app.include_router(status_router, prefix="/api/v1")
    test_app.include_router(admin_router, prefix="/api/v1")
    test_app.include_router(plugins_router, prefix="/api/v1")
    test_app.include_router(keys_router, prefix="/api/v1")
    test_app.include_router(metrics_router)
    test_app.include_router(health_router)

    @test_app.get("/health")
    async def health():
        return {"status": "ok"}

    test_app.state.orchestrator = _make_mock_orchestrator()
    test_app.state.llm_router = _make_mock_llm_router()
    test_app.state.start_time = time.monotonic()
    test_app.state.websocket_settings = WebSocketRuntimeSettings()
    test_app.state.security_settings = {
        "admin_ip_whitelist": [],
        "audit_db_path": str(tmp_path / "audit_trail.db"),
        "rate_limit": {"redis_url": None},
        "rate_limit_redis_url": None,
    }
    test_app.state.secrets_settings = {"backend": "local"}
    test_app.state.health_thresholds = HealthThresholds(disk_path=str(tmp_path))
    test_app.state.audit_trail = AuditTrail(str(tmp_path / "audit_trail.db"))
    test_app.state.websocket_audit_storage = WebSocketAuditStorage(
        str(tmp_path / "websocket_audit.db")
    )
    test_app.state.dead_letter_queue = DeadLetterQueueStorage(
        str(tmp_path / "dead_letter_queue.db")
    )
    test_app.state.error_analytics = ErrorAnalyticsStorage(
        str(tmp_path / "error_analytics.db")
    )
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
