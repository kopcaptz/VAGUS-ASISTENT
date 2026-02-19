"""
Admin endpoints.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..audit.audit_trail import AuditTrail
from ..dependencies import get_current_admin
from ..models import (
    AuditTrailLogEntry,
    CircuitBreakerStatsResponse,
    DeadLetterQueueEntryResponse,
    DeadLetterQueueManualFixRequest,
    DeadLetterQueueRetryRequest,
)

router = APIRouter(prefix="/admin", tags=["Admin"])


def _get_audit_storage(request: Request) -> AuditTrail:
    storage = getattr(request.app.state, "audit_trail", None)
    if not isinstance(storage, AuditTrail):
        raise HTTPException(status_code=503, detail="Audit storage is not available")
    return storage


def _get_dead_letter_queue_storage(request: Request):
    storage = getattr(request.app.state, "dead_letter_queue", None)
    if storage is None or not hasattr(storage, "list_entries"):
        raise HTTPException(status_code=503, detail="Dead Letter Queue storage is not available")
    return storage


def _get_error_analytics_storage(request: Request):
    storage = getattr(request.app.state, "error_analytics", None)
    if storage is None or not hasattr(storage, "build_analytics_snapshot"):
        raise HTTPException(status_code=503, detail="Error analytics storage is not available")
    return storage


def _get_memory_profiler(request: Request):
    storage = getattr(request.app.state, "memory_profiler", None)
    if storage is None or not hasattr(storage, "get_stats"):
        raise HTTPException(status_code=503, detail="Memory profiler is not available")
    return storage


def _state_to_public(raw_state: str) -> str:
    normalized = (raw_state or "").strip().upper()
    if normalized == "OPEN":
        return "open"
    if normalized == "HALF_OPEN":
        return "half-open"
    return "closed"


def _collect_circuit_breaker_stats(request: Request) -> list[dict[str, Any]]:
    llm_router = getattr(request.app.state, "llm_router", None)
    fallback_handler = getattr(llm_router, "fallback_handler", None) if llm_router else None
    breakers = getattr(fallback_handler, "_circuit_breakers", {}) if fallback_handler else {}
    if not isinstance(breakers, dict):
        return []

    result: list[dict[str, Any]] = []
    for provider_id, breaker in breakers.items():
        stats = {}
        if hasattr(breaker, "get_stats") and callable(breaker.get_stats):
            try:
                stats = breaker.get_stats() or {}
            except Exception:
                stats = {}
        state_obj = getattr(breaker, "state", None)
        state_name = getattr(state_obj, "name", "CLOSED")
        total_success = int(stats.get("total_success_count", stats.get("success_count", 0)) or 0)
        total_failure = int(stats.get("total_failure_count", stats.get("failure_count", 0)) or 0)
        total = total_success + total_failure
        success_rate = float(stats.get("success_rate", (total_success / total * 100.0) if total > 0 else 100.0))
        result.append(
            {
                "provider_id": str(provider_id),
                "state": _state_to_public(state_name),
                "failure_count": int(stats.get("failure_count", 0) or 0),
                "last_failure_time": stats.get("last_failure_iso") or stats.get("last_failure_time"),
                "success_rate": success_rate,
                "recovery_timeout": int(stats.get("recovery_timeout", 0) or 0),
                "failure_threshold": int(stats.get("failure_threshold", 0) or 0),
                "total_success_count": total_success,
                "total_failure_count": total_failure,
            }
        )
    result.sort(key=lambda item: item["provider_id"])
    return result


@router.get("/audit-logs", response_model=list[AuditTrailLogEntry])
async def get_audit_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    user_id: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    resource: Optional[str] = Query(default=None),
    current_admin: dict = Depends(get_current_admin),
):
    """Возвращает audit trail (только для admin)."""
    _ = current_admin
    storage = _get_audit_storage(request)
    rows = storage.list_logs(limit=limit, user_id=user_id, action=action, resource=resource)

    # Пытаемся декодировать details в JSON, если это JSON-строка.
    parsed_rows = []
    for row in rows:
        details = row.get("details")
        if isinstance(details, str):
            try:
                row["details"] = json.loads(details)
            except json.JSONDecodeError:
                pass
        parsed_rows.append(AuditTrailLogEntry(**row))
    return parsed_rows


@router.get("/dead-letter-queue", response_model=list[DeadLetterQueueEntryResponse])
async def get_dead_letter_queue(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    status: Optional[str] = Query(default=None),
    agent_type: Optional[str] = Query(default=None),
    current_admin: dict = Depends(get_current_admin),
):
    """Возвращает записи Dead Letter Queue (admin only)."""
    _ = current_admin
    storage = _get_dead_letter_queue_storage(request)
    rows = storage.list_entries(limit=limit, status=status, agent_type=agent_type)
    return [DeadLetterQueueEntryResponse(**row) for row in rows]


@router.post("/dead-letter-queue/{task_id}/retry")
async def retry_dead_letter_task(
    task_id: str,
    payload: DeadLetterQueueRetryRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
):
    """Пробует повторно выполнить задачу из DLQ."""
    _ = current_admin
    storage = _get_dead_letter_queue_storage(request)
    entry = storage.get_latest_entry(task_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"DLQ entry for task {task_id} not found")

    task_payload = entry.get("task_payload") or {}
    prompt = payload.prompt or task_payload.get("prompt")
    task_type = payload.task_type or task_payload.get("task_type", "default")
    if not prompt:
        raise HTTPException(
            status_code=400,
            detail="Retry prompt is missing. Provide it explicitly or perform manual fix.",
        )

    try:
        retry_count = int(entry.get("retry_count", 0) or 0) + 1
    except (TypeError, ValueError):
        retry_count = 1

    storage.mark_retry_requested(task_id=task_id, retry_count=retry_count)
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None or not hasattr(orchestrator, "execute_task"):
        raise HTTPException(status_code=503, detail="Orchestrator is not available")

    merged_metadata: dict[str, Any] = {}
    original_meta = task_payload.get("metadata", {})
    if isinstance(original_meta, dict):
        merged_metadata.update(original_meta)
    if isinstance(payload.metadata, dict):
        merged_metadata.update(payload.metadata)
    merged_metadata["retry_count"] = retry_count
    retry_task_id = f"{task_id}-retry-{retry_count}"

    result = await orchestrator.execute_task(
        task_id=retry_task_id,
        prompt=str(prompt),
        task_type=str(task_type),
        metadata=merged_metadata,
    )
    is_success = not (
        isinstance(result, dict) and (result.get("error") or result.get("success") is False)
    )
    storage.update_status(
        task_id=task_id,
        status="retry_success" if is_success else "retry_failed",
        retry_count=retry_count,
    )
    return {
        "task_id": task_id,
        "retry_task_id": retry_task_id,
        "retry_count": retry_count,
        "success": is_success,
        "result": result,
    }


@router.post(
    "/dead-letter-queue/{task_id}/manual-fix",
    response_model=DeadLetterQueueEntryResponse,
)
async def mark_dead_letter_manual_fix(
    task_id: str,
    payload: DeadLetterQueueManualFixRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
):
    """Помечает DLQ-задачу как исправленную вручную."""
    _ = current_admin
    storage = _get_dead_letter_queue_storage(request)
    updated = storage.mark_manual_fix(task_id=task_id, note=payload.note)
    if not updated:
        raise HTTPException(status_code=404, detail=f"DLQ entry for task {task_id} not found")
    row = storage.get_latest_entry(task_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"DLQ entry for task {task_id} not found")
    return DeadLetterQueueEntryResponse(**row)


@router.get("/circuit-breakers")
async def get_circuit_breakers(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
):
    """Статус всех circuit breakers + история состояний."""
    _ = current_admin
    breakers = _collect_circuit_breaker_stats(request)
    validated = [CircuitBreakerStatsResponse(**item).model_dump() for item in breakers]

    history = getattr(request.app.state, "circuit_breaker_history", [])
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "states": {item["provider_id"]: item["state"] for item in validated},
        }
    )
    history = history[-500:]
    request.app.state.circuit_breaker_history = history

    return {"breakers": validated, "history": history}


@router.post("/circuit-breakers/{provider_id}/reset")
async def reset_circuit_breaker(
    provider_id: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
):
    """Ручной reset circuit breaker."""
    _ = current_admin
    llm_router = getattr(request.app.state, "llm_router", None)
    fallback_handler = getattr(llm_router, "fallback_handler", None) if llm_router else None
    breakers = getattr(fallback_handler, "_circuit_breakers", {}) if fallback_handler else {}
    if not isinstance(breakers, dict) or provider_id not in breakers:
        raise HTTPException(status_code=404, detail=f"Circuit breaker '{provider_id}' not found")

    breaker = breakers[provider_id]
    if not hasattr(breaker, "reset") or not callable(breaker.reset):
        raise HTTPException(status_code=500, detail="Circuit breaker reset is not supported")
    breaker.reset()
    return {"provider_id": provider_id, "status": "reset"}


@router.get("/error-analytics")
async def get_error_analytics(
    request: Request,
    window_minutes: int = Query(default=60, ge=1, le=1440),
    top_sources_limit: int = Query(default=10, ge=1, le=100),
    current_admin: dict = Depends(get_current_admin),
):
    """Возвращает агрегированную аналитику ошибок."""
    _ = current_admin
    storage = _get_error_analytics_storage(request)

    metrics_context: dict[str, Any] = {}
    llm_router = getattr(request.app.state, "llm_router", None)
    if llm_router is not None and hasattr(llm_router, "get_stats"):
        try:
            stats = llm_router.get_stats() or {}
            if isinstance(stats, dict):
                metrics_context["requests"] = stats.get("requests", 0)
                cache = stats.get("cache", {})
                if isinstance(cache, dict):
                    metrics_context["cache_hit_rate_percent"] = cache.get("hit_rate_percent", 0.0)
        except Exception:
            metrics_context = {}

    return storage.build_analytics_snapshot(
        window_minutes=window_minutes,
        top_sources_limit=top_sources_limit,
        metrics_context=metrics_context,
    )


@router.get("/memory-stats")
async def get_memory_stats(
    request: Request,
    refresh: bool = Query(default=True),
    history_limit: int = Query(default=60, ge=1, le=1000),
    current_admin: dict = Depends(get_current_admin),
):
    """Возвращает runtime memory profiling + leak detection отчёт."""
    _ = current_admin
    profiler = _get_memory_profiler(request)
    return profiler.get_stats(refresh=refresh, history_limit=history_limit)
