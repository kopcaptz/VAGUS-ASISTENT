"""
Вспомогательные функции для визуализации данных.
"""

import time
from typing import Any, Dict, List


def format_uptime(seconds: float) -> str:
    """Форматирует uptime в читаемый вид."""
    if seconds < 60:
        return f"{seconds:.0f} сек"
    elif seconds < 3600:
        return f"{seconds / 60:.1f} мин"
    elif seconds < 86400:
        return f"{seconds / 3600:.1f} ч"
    return f"{seconds / 86400:.1f} дн"


def format_cost(cost: float) -> str:
    """Форматирует стоимость."""
    return f"${cost:.4f}"


def extract_metrics(status: Dict[str, Any]) -> Dict[str, Any]:
    """Извлекает ключевые метрики из статуса системы."""
    l1 = status.get("layer1_stats", {})
    return {
        "agents": status.get("layer2_agents_count", 0),
        "active_tasks": status.get("active_tasks_count", 0),
        "uptime": format_uptime(status.get("uptime_seconds", 0)),
        "requests": l1.get("requests", 0),
        "total_cost": format_cost(l1.get("total_cost", 0)),
        "cache_hit_rate": l1.get("cache", {}).get("hit_rate_percent", 0),
    }


def _parse_labels(raw_labels: str) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    if not raw_labels:
        return labels

    current = ""
    parts: List[str] = []
    in_quotes = False
    escaped = False
    for ch in raw_labels:
        if escaped:
            current += ch
            escaped = False
            continue
        if ch == "\\":
            current += ch
            escaped = True
            continue
        if ch == '"':
            current += ch
            in_quotes = not in_quotes
            continue
        if ch == "," and not in_quotes:
            parts.append(current)
            current = ""
            continue
        current += ch
    if current:
        parts.append(current)

    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"')
        labels[key] = value
    return labels


def parse_prometheus_samples(metrics_text: str) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for line in metrics_text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if " " not in raw:
            continue
        left, value_part = raw.split(None, 1)
        try:
            value = float(value_part.strip())
        except ValueError:
            continue

        labels: Dict[str, str] = {}
        metric_name = left
        if "{" in left and left.endswith("}"):
            metric_name, labels_raw = left.split("{", 1)
            labels = _parse_labels(labels_raw[:-1])
        samples.append({"name": metric_name, "labels": labels, "value": value})
    return samples


def sum_metric(samples: List[Dict[str, Any]], metric_name: str) -> float:
    return sum(sample["value"] for sample in samples if sample["name"] == metric_name)


def calculate_http_error_rate(samples: List[Dict[str, Any]]) -> float:
    total = 0.0
    errors = 0.0
    for sample in samples:
        if sample["name"] != "http_requests_total":
            continue
        value = float(sample["value"])
        total += value
        status = str(sample.get("labels", {}).get("status", ""))
        try:
            if int(status) >= 500:
                errors += value
        except ValueError:
            continue
    if total <= 0:
        return 0.0
    return (errors / total) * 100.0


def calculate_avg_request_latency_ms(samples: List[Dict[str, Any]]) -> float:
    total_duration = sum_metric(samples, "http_request_duration_seconds_sum")
    total_count = sum_metric(samples, "http_request_duration_seconds_count")
    if total_count <= 0:
        return 0.0
    return (total_duration / total_count) * 1000.0


def calculate_cache_hit_ratio(samples: List[Dict[str, Any]]) -> float:
    hits = sum_metric(samples, "cache_hits_total")
    misses = sum_metric(samples, "cache_misses_total")
    total = hits + misses
    if total <= 0:
        return 0.0
    return (hits / total) * 100.0


def build_performance_snapshot(metrics_text: str, system_status: Dict[str, Any]) -> Dict[str, Any]:
    samples = parse_prometheus_samples(metrics_text)
    layer1_stats = system_status.get("layer1_stats", {}) if isinstance(system_status, dict) else {}
    return {
        "timestamp": time.time(),
        "request_latency_ms": round(calculate_avg_request_latency_ms(samples), 2),
        "error_rate_percent": round(calculate_http_error_rate(samples), 2),
        "active_connections": round(sum_metric(samples, "websocket_connections_active"), 2),
        "cache_hit_ratio_percent": round(calculate_cache_hit_ratio(samples), 2),
        "llm_provider_cost_usd": float(layer1_stats.get("total_cost", 0.0) or 0.0),
    }


def append_history_snapshot(
    history: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
    *,
    window_hours: int = 24,
    now_ts: float | None = None,
) -> List[Dict[str, Any]]:
    now_value = float(now_ts if now_ts is not None else time.time())
    cutoff = now_value - (window_hours * 3600)
    merged = [*history, snapshot]
    return [item for item in merged if float(item.get("timestamp", 0.0)) >= cutoff]


def circuit_breaker_state_to_numeric(state: str) -> int:
    normalized = (state or "").strip().lower()
    if normalized == "open":
        return 1
    if normalized in {"half-open", "half_open"}:
        return 2
    return 0


def append_circuit_breaker_history(
    history: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
    *,
    window_hours: int = 24,
    now_ts: float | None = None,
) -> List[Dict[str, Any]]:
    now_value = float(now_ts if now_ts is not None else time.time())
    ts_value = snapshot.get("timestamp", now_value)
    try:
        snapshot_ts = float(ts_value)
    except (TypeError, ValueError):
        snapshot_ts = now_value

    prepared = dict(snapshot)
    prepared["timestamp"] = snapshot_ts
    cutoff = now_value - (window_hours * 3600)
    merged = [*history, prepared]
    return [item for item in merged if float(item.get("timestamp", 0.0)) >= cutoff]


def flatten_circuit_breaker_history(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in history:
        timestamp = float(item.get("timestamp", 0.0))
        states = item.get("states", {})
        if not isinstance(states, dict):
            continue
        for provider_id, state in states.items():
            rows.append(
                {
                    "timestamp": timestamp,
                    "provider_id": str(provider_id),
                    "state_numeric": circuit_breaker_state_to_numeric(str(state)),
                }
            )
    return rows


def extract_error_rates(analytics_snapshot: Dict[str, Any]) -> Dict[str, float]:
    by_type = analytics_snapshot.get("error_rate_by_type", {})
    rates = by_type.get("rates_percent", {}) if isinstance(by_type, dict) else {}
    if not isinstance(rates, dict):
        return {"transient": 0.0, "permanent": 0.0, "infrastructure": 0.0}
    return {
        "transient": float(rates.get("transient", 0.0) or 0.0),
        "permanent": float(rates.get("permanent", 0.0) or 0.0),
        "infrastructure": float(rates.get("infrastructure", 0.0) or 0.0),
    }
