"""
Prometheus metrics registry and /metrics endpoint.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Iterable, Tuple

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


def _escape_label_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
    return escaped


def _format_labels(label_names: Tuple[str, ...], label_values: Tuple[str, ...]) -> str:
    if not label_names:
        return ""
    parts = []
    for name, value in zip(label_names, label_values):
        parts.append(f'{name}="{_escape_label_value(value)}"')
    return "{" + ",".join(parts) + "}"


class _CounterMetric:
    def __init__(self, name: str, help_text: str, label_names: Iterable[str] = ()):
        self.name = name
        self.help_text = help_text
        self.label_names = tuple(label_names)
        self._samples: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, *label_values: str, amount: float = 1.0) -> None:
        labels = tuple(str(v) for v in label_values)
        with self._lock:
            self._samples[labels] = self._samples.get(labels, 0.0) + amount

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        with self._lock:
            if not self._samples and not self.label_names:
                lines.append(f"{self.name} 0")
            else:
                for labels in sorted(self._samples):
                    value = self._samples[labels]
                    lines.append(
                        f"{self.name}{_format_labels(self.label_names, labels)} {value}"
                    )
        return "\n".join(lines)


class _GaugeMetric:
    def __init__(self, name: str, help_text: str, label_names: Iterable[str] = ()):
        self.name = name
        self.help_text = help_text
        self.label_names = tuple(label_names)
        self._samples: Dict[Tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, *label_values: str) -> None:
        labels = tuple(str(v) for v in label_values)
        with self._lock:
            self._samples[labels] = float(value)

    def inc(self, *label_values: str, amount: float = 1.0) -> None:
        labels = tuple(str(v) for v in label_values)
        with self._lock:
            self._samples[labels] = self._samples.get(labels, 0.0) + amount

    def dec(self, *label_values: str, amount: float = 1.0) -> None:
        self.inc(*label_values, amount=-amount)

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        with self._lock:
            if not self._samples and not self.label_names:
                lines.append(f"{self.name} 0")
            else:
                for labels in sorted(self._samples):
                    value = self._samples[labels]
                    lines.append(
                        f"{self.name}{_format_labels(self.label_names, labels)} {value}"
                    )
        return "\n".join(lines)


class _HistogramMetric:
    def __init__(
        self,
        name: str,
        help_text: str,
        label_names: Iterable[str] = (),
        buckets: Iterable[float] = (),
    ):
        self.name = name
        self.help_text = help_text
        self.label_names = tuple(label_names)
        self.buckets = tuple(sorted(float(bucket) for bucket in buckets))
        self._samples: Dict[Tuple[str, ...], Dict[str, object]] = {}
        self._lock = threading.Lock()

    def observe(self, value: float, *label_values: str) -> None:
        labels = tuple(str(v) for v in label_values)
        numeric_value = float(value)
        with self._lock:
            if labels not in self._samples:
                self._samples[labels] = {
                    "sum": 0.0,
                    "count": 0.0,
                    "bucket_counts": [0.0 for _ in self.buckets],
                }
            item = self._samples[labels]
            item["sum"] = float(item["sum"]) + numeric_value
            item["count"] = float(item["count"]) + 1.0
            bucket_counts = item["bucket_counts"]
            assert isinstance(bucket_counts, list)
            for idx, upper in enumerate(self.buckets):
                if numeric_value <= upper:
                    bucket_counts[idx] = float(bucket_counts[idx]) + 1.0

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()

    def render(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        with self._lock:
            if not self._samples and not self.label_names:
                for upper in self.buckets:
                    lines.append(f'{self.name}_bucket{{le="{upper}"}} 0')
                lines.append(f'{self.name}_bucket{{le="+Inf"}} 0')
                lines.append(f"{self.name}_sum 0")
                lines.append(f"{self.name}_count 0")
                return "\n".join(lines)

            for labels in sorted(self._samples):
                item = self._samples[labels]
                metric_count = float(item["count"])
                metric_sum = float(item["sum"])
                bucket_counts = item["bucket_counts"]
                assert isinstance(bucket_counts, list)

                for idx, upper in enumerate(self.buckets):
                    labels_with_le_names = self.label_names + ("le",)
                    labels_with_le_values = labels + (str(upper),)
                    value = float(bucket_counts[idx])
                    lines.append(
                        f"{self.name}_bucket{_format_labels(labels_with_le_names, labels_with_le_values)} {value}"
                    )

                labels_with_inf_names = self.label_names + ("le",)
                labels_with_inf_values = labels + ("+Inf",)
                lines.append(
                    f"{self.name}_bucket{_format_labels(labels_with_inf_names, labels_with_inf_values)} {metric_count}"
                )
                lines.append(
                    f"{self.name}_sum{_format_labels(self.label_names, labels)} {metric_sum}"
                )
                lines.append(
                    f"{self.name}_count{_format_labels(self.label_names, labels)} {metric_count}"
                )
        return "\n".join(lines)


class PrometheusMetricsRegistry:
    def __init__(self) -> None:
        self.http_requests_total = _CounterMetric(
            "http_requests_total",
            "Total number of HTTP requests",
            ("method", "endpoint", "status"),
        )
        self.http_request_duration_seconds = _HistogramMetric(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ("method", "endpoint"),
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
        )
        self.websocket_connections_active = _GaugeMetric(
            "websocket_connections_active",
            "Number of currently active websocket connections",
        )
        self.task_execution_total = _CounterMetric(
            "task_execution_total",
            "Total executed tasks by agent and status",
            ("agent_type", "status"),
        )
        self.llm_requests_total = _CounterMetric(
            "llm_requests_total",
            "Total LLM requests by provider/model/status",
            ("provider", "model", "status"),
        )
        self.cache_hits_total = _CounterMetric(
            "cache_hits_total",
            "Total cache hit events",
        )
        self.cache_misses_total = _CounterMetric(
            "cache_misses_total",
            "Total cache miss events",
        )
        self.circuit_breaker_state = _GaugeMetric(
            "circuit_breaker_state",
            "Circuit breaker state (0=closed,1=open,2=half-open)",
        )

    def render(self) -> str:
        parts = [
            self.http_requests_total.render(),
            self.http_request_duration_seconds.render(),
            self.websocket_connections_active.render(),
            self.task_execution_total.render(),
            self.llm_requests_total.render(),
            self.cache_hits_total.render(),
            self.cache_misses_total.render(),
            self.circuit_breaker_state.render(),
        ]
        return "\n\n".join(parts) + "\n"

    def reset(self) -> None:
        self.http_requests_total.reset()
        self.http_request_duration_seconds.reset()
        self.websocket_connections_active.reset()
        self.task_execution_total.reset()
        self.llm_requests_total.reset()
        self.cache_hits_total.reset()
        self.cache_misses_total.reset()
        self.circuit_breaker_state.reset()


prometheus_metrics = PrometheusMetricsRegistry()


def observe_http_request(method: str, endpoint: str, status_code: int, duration_seconds: float) -> None:
    method_normalized = method.upper()
    endpoint_normalized = endpoint or "unknown"
    status_label = str(int(status_code))
    prometheus_metrics.http_requests_total.inc(
        method_normalized,
        endpoint_normalized,
        status_label,
    )
    prometheus_metrics.http_request_duration_seconds.observe(
        max(0.0, float(duration_seconds)),
        method_normalized,
        endpoint_normalized,
    )


def increment_websocket_connections() -> None:
    prometheus_metrics.websocket_connections_active.inc()


def decrement_websocket_connections() -> None:
    prometheus_metrics.websocket_connections_active.dec()


def record_task_execution(agent_type: str, status: str) -> None:
    prometheus_metrics.task_execution_total.inc(agent_type or "unknown", status or "unknown")


def record_llm_request(provider: str, model: str, status: str) -> None:
    prometheus_metrics.llm_requests_total.inc(
        provider or "unknown",
        model or "unknown",
        status or "unknown",
    )


def record_cache_hit() -> None:
    prometheus_metrics.cache_hits_total.inc()


def record_cache_miss() -> None:
    prometheus_metrics.cache_misses_total.inc()


def set_circuit_breaker_state(value: int) -> None:
    # 0=closed, 1=open, 2=half-open
    sanitized = 0 if value < 0 else 2 if value > 2 else value
    prometheus_metrics.circuit_breaker_state.set(float(sanitized))


def update_circuit_breaker_state_from_router(llm_router: object) -> None:
    state_by_name = {"CLOSED": 0, "OPEN": 1, "HALF_OPEN": 2}
    fallback_handler = getattr(llm_router, "fallback_handler", None)
    breakers = getattr(fallback_handler, "_circuit_breakers", {}) if fallback_handler else {}
    if not isinstance(breakers, dict) or not breakers:
        set_circuit_breaker_state(0)
        return

    highest = 0
    for breaker in breakers.values():
        state = getattr(breaker, "state", None)
        state_name = getattr(state, "name", None)
        highest = max(highest, state_by_name.get(str(state_name), 0))
    set_circuit_breaker_state(highest)


router = APIRouter(tags=["Monitoring"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics_endpoint(request: Request) -> Response:
    llm_router = getattr(request.app.state, "llm_router", None)
    if llm_router is not None:
        update_circuit_breaker_state_from_router(llm_router)
    return Response(
        content=prometheus_metrics.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    """Captures HTTP throughput and latency metrics."""

    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            route = request.scope.get("route")
            endpoint = getattr(route, "path", request.url.path)
            observe_http_request(
                request.method,
                endpoint or request.url.path,
                status_code,
                time.monotonic() - started_at,
            )


__all__ = [
    "router",
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
    "HTTPMetricsMiddleware",
]
