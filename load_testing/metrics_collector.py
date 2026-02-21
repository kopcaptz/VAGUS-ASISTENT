"""
Metrics collector for load testing.
Collects task duration, Synaptic buffer, Redis stream length, PostgreSQL stats.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx


async def collect_metrics(
    base_url: str = "http://localhost:8000",
    redis_url: Optional[str] = None,
    token: Optional[str] = None,
) -> dict[str, Any]:
    """
    Collect metrics from monitoring endpoints.

    Args:
        base_url: API base URL (e.g. http://localhost:8000)
        redis_url: Optional Redis URL for direct XLEN (if no API access)
        token: JWT Bearer token for /monitoring/* (required)

    Returns:
        Dict with task_duration_sec, synaptic_buffer_size, synaptic_events_processed,
        redis_stream_length, redis_dlq_count, postgres_query_time_ms, postgres_pool_size
    """
    result: dict[str, Any] = {
        "task_duration_sec": None,
        "synaptic_buffer_size": None,
        "synaptic_events_processed": None,
        "synaptic_flush_count": None,
        "redis_stream_length": None,
        "redis_dlq_count": None,
        "redis_available": False,
        "postgres_query_time_ms": None,
        "postgres_pool_size": None,
        "postgres_available": False,
    }

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        base = base_url.rstrip("/")

        # Redis monitoring
        try:
            r = await client.get(f"{base}/api/v1/monitoring/redis", headers=headers)
            if r.status_code == 200:
                data = r.json()
                result["redis_available"] = data.get("available", False)
                result["redis_dlq_count"] = data.get("dlq_count", 0)
                if data.get("available") and redis_url:
                    try:
                        import redis.asyncio as redis
                        rd = redis.from_url(redis_url, decode_responses=True)
                        stream = data.get("stream_name", "vagus:events:stream")
                        result["redis_stream_length"] = await rd.xlen(stream)
                        await rd.aclose()
                    except Exception:
                        pass
        except Exception:
            pass

        # Synaptic monitoring
        try:
            r = await client.get(f"{base}/api/v1/monitoring/synaptic", headers=headers)
            if r.status_code == 200:
                data = r.json()
                if data.get("available"):
                    result["synaptic_buffer_size"] = data.get("buffer_size", 0)
                    result["synaptic_events_processed"] = data.get("events_processed", 0)
                    result["synaptic_flush_count"] = data.get("flush_count", 0)
        except Exception:
            pass

        # PostgreSQL monitoring
        try:
            r = await client.get(f"{base}/api/v1/monitoring/postgres", headers=headers)
            if r.status_code == 200:
                data = r.json()
                if data.get("available"):
                    result["postgres_available"] = True
                    result["postgres_query_time_ms"] = data.get("query_time_ms")
                    result["postgres_pool_size"] = data.get("pool_size")
        except Exception:
            pass

    return result


def percentile(values: list[float], p: float) -> float:
    """Compute percentile (0-100) of sorted values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100)
    f = int(k)
    c = f + 1 if f + 1 < len(sorted_vals) else f
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f]) if f != c else sorted_vals[f]
