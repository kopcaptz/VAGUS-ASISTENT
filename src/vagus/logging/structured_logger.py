"""
Structured JSON logging helpers with trace context propagation.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Dict, Iterator, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from vagus.layer3.api.auth import decode_access_token


_trace_id_ctx: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_agent_id_ctx: ContextVar[Optional[str]] = ContextVar("agent_id", default=None)
_component_ctx: ContextVar[Optional[str]] = ContextVar("component", default=None)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def generate_request_id() -> str:
    return uuid.uuid4().hex


def get_trace_id() -> Optional[str]:
    return _trace_id_ctx.get()


@contextmanager
def logging_context(
    *,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    component: Optional[str] = None,
) -> Iterator[None]:
    tokens = []
    try:
        if trace_id is not None:
            tokens.append((_trace_id_ctx, _trace_id_ctx.set(trace_id)))
        if request_id is not None:
            tokens.append((_request_id_ctx, _request_id_ctx.set(request_id)))
        if user_id is not None:
            tokens.append((_user_id_ctx, _user_id_ctx.set(user_id)))
        if agent_id is not None:
            tokens.append((_agent_id_ctx, _agent_id_ctx.set(agent_id)))
        if component is not None:
            tokens.append((_component_ctx, _component_ctx.set(component)))
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


class StructuredJSONFormatter(logging.Formatter):
    """JSON formatter with trace-aware context fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, object] = {
            "timestamp": _utc_now_iso(),
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or _trace_id_ctx.get(),
            "request_id": getattr(record, "request_id", None) or _request_id_ctx.get(),
            "user_id": getattr(record, "user_id", None) or _user_id_ctx.get(),
            "agent_id": getattr(record, "agent_id", None) or _agent_id_ctx.get(),
            "duration_ms": getattr(record, "duration_ms", None),
            "component": getattr(record, "component", None)
            or _component_ctx.get()
            or record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(level: int = logging.INFO, force: bool = False) -> None:
    """
    Enables structured JSON logging for vagus.* loggers.
    """
    root = logging.getLogger("vagus")
    root.setLevel(level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if hasattr(handler.stream, "reconfigure"):
            try:
                handler.stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
        handler.setFormatter(StructuredJSONFormatter())
        root.addHandler(handler)
        return

    for handler in root.handlers:
        formatter = handler.formatter
        if force or not isinstance(formatter, StructuredJSONFormatter):
            handler.setFormatter(StructuredJSONFormatter())


def _extract_user_id_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if payload is None:
        return None
    return payload.get("sub")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """Injects trace context into HTTP requests and logs access lines."""

    def __init__(self, app, *, component: str = "api"):
        super().__init__(app)
        self.component = component
        self.logger = logging.getLogger("vagus.layer3.api.structured")

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("x-trace-id") or generate_trace_id()
        request_id = request.headers.get("x-request-id") or generate_request_id()
        user_id = _extract_user_id_from_request(request)
        started_at = time.monotonic()

        request.state.trace_id = trace_id
        request.state.request_id = request_id

        with logging_context(
            trace_id=trace_id,
            request_id=request_id,
            user_id=user_id,
            component=self.component,
        ):
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = round((time.monotonic() - started_at) * 1000, 2)
                self.logger.exception(
                    "HTTP request failed",
                    extra={
                        "duration_ms": duration_ms,
                        "component": self.component,
                        "request_id": request_id,
                        "trace_id": trace_id,
                        "user_id": user_id,
                    },
                )
                raise

            duration_ms = round((time.monotonic() - started_at) * 1000, 2)
            self.logger.info(
                "HTTP request completed",
                extra={
                    "duration_ms": duration_ms,
                    "component": self.component,
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "user_id": user_id,
                },
            )

        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Request-Id"] = request_id
        return response


__all__ = [
    "StructuredJSONFormatter",
    "StructuredLoggingMiddleware",
    "configure_structured_logging",
    "generate_trace_id",
    "generate_request_id",
    "get_trace_id",
    "logging_context",
]
