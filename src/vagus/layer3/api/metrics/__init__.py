"""Metrics endpoints and instrumentation helpers."""

from .prometheus import (
    HTTPMetricsMiddleware,
    decrement_websocket_connections,
    increment_websocket_connections,
    observe_http_request,
    prometheus_metrics,
    record_cache_hit,
    record_cache_miss,
    record_llm_request,
    record_task_execution,
    router as metrics_router,
    set_circuit_breaker_state,
    update_circuit_breaker_state_from_router,
)

__all__ = [
    "metrics_router",
    "HTTPMetricsMiddleware",
    "prometheus_metrics",
    "observe_http_request",
    "increment_websocket_connections",
    "decrement_websocket_connections",
    "record_task_execution",
    "record_llm_request",
    "record_cache_hit",
    "record_cache_miss",
    "set_circuit_breaker_state",
    "update_circuit_breaker_state_from_router",
]
