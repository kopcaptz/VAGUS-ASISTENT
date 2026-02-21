"""
Fallback monitor utilities for chaos tests.
Detect whether components use in-memory fallback vs Redis/Postgres.
"""
from typing import Any

from vagus.layer2.communication.blackboard import SharedBlackboard
from vagus.layer2.communication import CommunicationLayer


def is_blackboard_using_memory(blackboard: SharedBlackboard) -> bool:
    """Return True if Blackboard uses in-memory backend (not Redis)."""
    return getattr(blackboard, "_redis", None) is None


def is_event_bus_using_memory(comm: CommunicationLayer) -> bool:
    """Return True if Event Bus uses in-memory backend (not Redis)."""
    if not getattr(comm, "_event_bus_enabled", True):
        return True
    if not getattr(comm, "_redis_initialized", False):
        return True
    if getattr(comm, "_streams_client", None) is not None:
        return False
    if getattr(comm, "_redis", None) is not None:
        return False
    return True


def assert_api_returns_graceful_error(
    response: Any,
    expected_status_min: int = 500,
) -> None:
    """
    Assert that API response indicates graceful error handling:
    - Status code >= expected_status_min (default 500)
    - Response has body (not empty crash)
    """
    status = getattr(response, "status_code", None) or getattr(response, "status", None)
    assert status is not None, "Response has no status_code/status"
    assert status >= expected_status_min, (
        f"Expected status >= {expected_status_min}, got {status}"
    )
    body = getattr(response, "text", None) or getattr(response, "body", None)
    if body is not None and isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    assert body is not None, "Response has no body"
    assert len(str(body).strip()) > 0, "Response body is empty (possible crash)"
