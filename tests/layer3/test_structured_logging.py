"""Tests for structured logging and trace propagation."""

import io
import json
import logging

from vagus.logging import (
    StructuredJSONFormatter,
    configure_structured_logging,
    generate_trace_id,
    logging_context,
)


def test_structured_json_formatter_includes_context_fields():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(StructuredJSONFormatter())

    logger = logging.getLogger("vagus.test.structured")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    with logging_context(
        trace_id="trace-123",
        request_id="req-123",
        user_id="user-1",
        agent_id="agent-7",
        component="unit-test",
    ):
        logger.info("hello structured")

    raw = stream.getvalue().strip()
    payload = json.loads(raw)
    assert payload["message"] == "hello structured"
    assert payload["trace_id"] == "trace-123"
    assert payload["request_id"] == "req-123"
    assert payload["user_id"] == "user-1"
    assert payload["agent_id"] == "agent-7"
    assert payload["component"] == "unit-test"


def test_structured_logging_middleware_sets_trace_headers(client):
    configure_structured_logging(force=True)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Trace-Id")
    assert response.headers.get("X-Request-Id")


def test_generate_trace_id_has_expected_shape():
    trace_id = generate_trace_id()
    assert isinstance(trace_id, str)
    assert len(trace_id) == 32
