"""
Shared fixtures for Layer 3 tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from vagus.layer3.api.auth import create_access_token
from vagus.layer3.api.main import app
from vagus.layer3.api.routers.tasks import _task_store


@pytest.fixture(autouse=True)
def clear_task_store():
    """Clears the in-memory task store before each test."""
    _task_store.clear()
    yield
    _task_store.clear()


@pytest.fixture
def mock_orchestrator():
    """Creates a mock TaskOrchestrator."""
    mock = AsyncMock()
    mock.agents = []
    mock.execute_task = AsyncMock(return_value={
        "content": "Test result",
        "metadata": {"agent": "researcher"},
    })
    return mock


@pytest.fixture
def client(mock_orchestrator):
    """TestClient with mocked orchestrator and llm_router."""
    app.state.orchestrator = mock_orchestrator
    app.state.llm_router = MagicMock()
    app.state.llm_router.get_stats.return_value = {"requests": 0, "total_cost": 0.0}
    app.state.start_time = 0
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers():
    """Returns a dict with a valid Authorization header."""
    token = create_access_token({"sub": "admin", "roles": ["admin", "user"]})
    return {"Authorization": f"Bearer {token}"}
