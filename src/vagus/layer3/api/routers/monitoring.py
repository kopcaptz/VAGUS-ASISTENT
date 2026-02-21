"""
Monitoring router — Redis Streams, PostgreSQL, artifact graph, synaptic metrics.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_current_user, get_orchestrator

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])

CONSUMER_GROUPS = ["memory_consolidation", "synaptic_training"]


@router.get("/redis")
async def get_monitoring_redis(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Redis Streams: consumer groups, pending messages, DLQ size.
    Returns {"available": false, "error": "..."} when Redis Streams not enabled.
    """
    result: dict[str, Any] = {"available": False, "stream_name": None, "consumer_groups": [], "dlq_count": 0}
    event_bus = getattr(orchestrator, "event_bus", None)
    if not event_bus or not getattr(event_bus, "uses_streams", False):
        result["error"] = "Redis Streams not enabled"
        return result

    streams_client = getattr(event_bus, "_streams_client", None)
    if not streams_client:
        result["error"] = "Redis Streams client not configured"
        return result

    redis_client = getattr(streams_client, "_redis", None)
    stream_name = getattr(event_bus, "_stream_name", None) or "vagus:events:stream"
    if not redis_client:
        result["error"] = "Redis client not available"
        return result

    try:
        result["available"] = True
        result["stream_name"] = stream_name

        try:
            groups_raw = await redis_client.xinfo_groups(stream_name)
        except Exception as e:
            result["consumer_groups"] = []
            result["groups_error"] = str(e)
            groups_raw = []

        def _to_dict(raw: Any) -> dict:
            """Parse redis flat [k,v,k,v] list or dict to dict."""
            if isinstance(raw, dict):
                return raw
            if isinstance(raw, (list, tuple)):
                d = {}
                for i in range(0, len(raw) - 1, 2):
                    k, v = raw[i], raw[i + 1]
                    if isinstance(k, bytes):
                        k = k.decode()
                    if isinstance(v, bytes):
                        v = v.decode()
                    d[k] = v
                return d
            return {}

        for group_row in groups_raw:
            group_info = _to_dict(group_row)
            group_name = str(group_info.get("name", "") or "")
            last_id = str(group_info.get("last-delivered-id", "0-0") or "0-0")
            consumers_count = int(group_info.get("consumers", 0) or 0)
            pending_count = int(group_info.get("pending", 0) or 0)

            result["consumer_groups"].append({
                "name": group_name,
                "last_delivered_id": last_id,
                "consumers": consumers_count,
                "pending": pending_count,
            })

        dlq_name = f"{stream_name}_dlq"
        try:
            result["dlq_count"] = await redis_client.xlen(dlq_name)
        except Exception:
            result["dlq_count"] = 0

    except Exception as exc:
        result["available"] = False
        result["error"] = str(exc)

    return result


@router.get("/postgres")
async def get_monitoring_postgres(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Database metrics: artifact count, relationship count, pool stats (PG only), query time.
    Supports both PostgreSQL and SQLite backends.
    """
    result: dict[str, Any] = {"available": False, "backend": "unknown", "artifacts_count": 0, "relationships_count": 0, "query_time_ms": None}
    memory_manager = getattr(orchestrator, "memory_manager", None)
    if not memory_manager:
        result["error"] = "Memory manager not available"
        return result

    artifact_kb = getattr(memory_manager, "_artifact_kb", None) or getattr(memory_manager, "artifact_kb", None)
    if not artifact_kb:
        result["error"] = "Artifact KB not available"
        return result

    is_pg = hasattr(artifact_kb, "_pool") and artifact_kb._pool is not None
    result["backend"] = "postgres" if is_pg else "sqlite"
    result["available"] = True

    try:
        start = time.perf_counter()
        if is_pg:
            async with artifact_kb._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) as c FROM artifacts")
                result["artifacts_count"] = int(row["c"]) if row else 0
                row = await conn.fetchrow("SELECT COUNT(*) as c FROM artifact_relationships")
                result["relationships_count"] = int(row["c"]) if row else 0
            try:
                result["pool_size"] = len(getattr(artifact_kb._pool, "_holders", []))
            except Exception:
                result["pool_size"] = None
            result["pool_min_size"] = getattr(artifact_kb, "_min_size", None)
            result["pool_max_size"] = getattr(artifact_kb, "_max_size", None)
        else:
            conn = getattr(artifact_kb, "_conn", None)
            if conn:
                async with conn.execute("SELECT COUNT(*) FROM artifacts") as cur:
                    row = await cur.fetchone()
                    result["artifacts_count"] = int(row[0]) if row else 0
                async with conn.execute("SELECT COUNT(*) FROM artifact_relationships") as cur:
                    row = await cur.fetchone()
                    result["relationships_count"] = int(row[0]) if row else 0
        result["query_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
    except Exception as exc:
        result["error"] = str(exc)

    return result


@router.get("/artifact-graph")
async def get_monitoring_artifact_graph(
    request: Request,
    tenant_id: Optional[str] = None,
    limit: int = 500,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Artifact graph data: nodes and edges for visualization.
    """
    result: dict[str, Any] = {"edges": [], "available": False}
    memory_manager = getattr(orchestrator, "memory_manager", None)
    if not memory_manager:
        result["error"] = "Memory manager not available"
        return result

    artifact_kb = getattr(memory_manager, "_artifact_kb", None) or getattr(memory_manager, "artifact_kb", None)
    if not artifact_kb:
        result["error"] = "Artifact KB not available"
        return result

    if not hasattr(artifact_kb, "get_relationships_for_graph"):
        result["error"] = "Artifact KB does not support graph export"
        return result

    try:
        edges = await artifact_kb.get_relationships_for_graph(tenant_id=tenant_id, limit=limit)
        result["edges"] = edges
        result["available"] = True
        nodes = set()
        for e in edges:
            nodes.add(e["source_id"])
            nodes.add(e["target_id"])
        result["nodes_count"] = len(nodes)
        result["edges_count"] = len(edges)
    except Exception as exc:
        result["error"] = str(exc)

    return result


@router.get("/synaptic")
async def get_monitoring_synaptic(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    SynapticTrainingHandler stats: buffer_size, events_processed, flush_count, flush_history.
    """
    result: dict[str, Any] = {"available": False}
    synaptic_handler = getattr(orchestrator, "synaptic_handler", None)
    if not synaptic_handler:
        result["error"] = "Synaptic handler not available"
        return result

    if not hasattr(synaptic_handler, "get_stats"):
        result["error"] = "Synaptic handler does not expose stats"
        return result

    try:
        stats = synaptic_handler.get_stats()
        result["available"] = True
        result.update(stats)
    except Exception as exc:
        result["error"] = str(exc)

    return result
