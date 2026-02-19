"""Тесты Pydantic-моделей Layer 3."""

import pytest
from vagus.layer3.api.models import (
    AgentInfoResponse,
    ErrorResponse,
    RefreshTokenRequest,
    SystemStatusResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskListItem,
    TaskStatus,
    TaskStatusResponse,
    TokenRequest,
    TokenResponse,
    WebSocketStreamChunk,
)


def test_task_status_enum_values():
    assert TaskStatus.PENDING == "pending"
    assert TaskStatus.IN_PROGRESS == "in_progress"
    assert TaskStatus.COMPLETED == "completed"
    assert TaskStatus.FAILED == "failed"


def test_task_create_request_valid():
    req = TaskCreateRequest(prompt="Hello world")
    assert req.prompt == "Hello world"
    assert req.task_type == "default"
    assert req.stream is False
    assert req.metadata is None


def test_task_create_request_all_fields():
    req = TaskCreateRequest(
        prompt="Test", task_type="code", stream=True, metadata={"key": "val"}
    )
    assert req.task_type == "code"
    assert req.stream is True
    assert req.metadata == {"key": "val"}


def test_task_create_request_empty_prompt_fails():
    with pytest.raises(Exception):
        TaskCreateRequest(prompt="")


def test_task_create_response():
    resp = TaskCreateResponse(
        task_id="abc-123",
        status_endpoint="/api/v1/tasks/abc-123",
        stream_endpoint="/api/v1/tasks/ws/abc-123",
    )
    assert resp.task_id == "abc-123"
    assert resp.status == TaskStatus.PENDING
    assert resp.created_at is not None


def test_task_status_response():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    resp = TaskStatusResponse(
        task_id="t1",
        status=TaskStatus.COMPLETED,
        result={"content": "done"},
        created_at=now,
        updated_at=now,
    )
    assert resp.task_id == "t1"
    assert resp.result == {"content": "done"}


def test_agent_info_response():
    resp = AgentInfoResponse(
        name="researcher",
        description="Research agent",
        task_types=["research", "search"],
        is_available=True,
    )
    assert resp.name == "researcher"
    assert len(resp.task_types) == 2


def test_system_status_response():
    resp = SystemStatusResponse(
        layer1_stats={"requests": 10},
        layer2_agents_count=3,
        active_tasks_count=1,
        uptime_seconds=120.5,
    )
    assert resp.layer2_agents_count == 3
    assert resp.uptime_seconds == 120.5


def test_token_request():
    req = TokenRequest(username="admin", password="admin")
    assert req.username == "admin"


def test_token_response():
    resp = TokenResponse(access_token="abc", refresh_token="def")
    assert resp.token_type == "bearer"


def test_websocket_stream_chunk():
    chunk = WebSocketStreamChunk(content="hello", done=False)
    assert chunk.content == "hello"
    assert chunk.done is False

    done_chunk = WebSocketStreamChunk(done=True)
    assert done_chunk.done is True


def test_error_response():
    err = ErrorResponse(detail="something went wrong")
    assert err.detail == "something went wrong"


def test_task_list_item():
    from datetime import datetime, timezone

    item = TaskListItem(
        task_id="x", status=TaskStatus.PENDING, created_at=datetime.now(timezone.utc)
    )
    assert item.task_id == "x"


def test_refresh_token_request():
    req = RefreshTokenRequest(refresh_token="tok123")
    assert req.refresh_token == "tok123"
