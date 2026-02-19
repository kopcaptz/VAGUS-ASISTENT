"""
Роутер задач: CRUD + WebSocket стриминг.
"""

import asyncio
import json
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from vagus.layer0.logging import get_logger

from ..audit.audit_trail import AuditTrail
from ..auth import decode_access_token
from ..dependencies import get_current_user, get_orchestrator
from ..models import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskListItem,
    TaskStatus,
    TaskStatusResponse,
    WebSocketAuditLogEntry,
)
from ..websocket_security import WebSocketAuditStorage, WebSocketRuntimeSettings

router = APIRouter(prefix="/tasks", tags=["Tasks"])
logger = get_logger("layer3.api.tasks")

task_store: Dict[str, dict] = {}

WS_CLOSE_NORMAL = 1000
WS_CLOSE_POLICY_VIOLATION = 1008
WS_CLOSE_INTERNAL_ERROR = 1011
WS_CLOSE_TRY_AGAIN_LATER = 1013
WS_CLOSE_MESSAGE_TOO_BIG = 1009


class _WebSocketConnectionState:
    """Mutable runtime state for one WebSocket connection."""

    def __init__(self) -> None:
        self.last_pong_monotonic = time.monotonic()
        self.message_timestamps: Deque[float] = deque()
        self.closed = False
        self.close_code: Optional[int] = None
        self.close_reason: Optional[str] = None


def _get_runtime_settings(websocket: WebSocket) -> WebSocketRuntimeSettings:
    settings = getattr(websocket.app.state, "websocket_settings", None)
    if isinstance(settings, WebSocketRuntimeSettings):
        return settings
    return WebSocketRuntimeSettings()


def _get_audit_storage(app) -> WebSocketAuditStorage:
    storage = getattr(app.state, "websocket_audit_storage", None)
    if isinstance(storage, WebSocketAuditStorage):
        return storage
    fallback_storage = WebSocketAuditStorage()
    app.state.websocket_audit_storage = fallback_storage
    return fallback_storage


def _get_audit_trail(app) -> Optional[AuditTrail]:
    storage = getattr(app.state, "audit_trail", None)
    if isinstance(storage, AuditTrail):
        return storage
    return None


def _log_audit(
    audit_storage: WebSocketAuditStorage,
    *,
    app,
    event_type: str,
    user_id: Optional[str],
    task_id: Optional[str],
    message_size_bytes: Optional[int] = None,
    message_type: Optional[str] = None,
    close_code: Optional[int] = None,
    reason: Optional[str] = None,
    duration_seconds: Optional[float] = None,
) -> None:
    try:
        audit_storage.log_event(
            event_type=event_type,
            user_id=user_id,
            task_id=task_id,
            message_size_bytes=message_size_bytes,
            message_type=message_type,
            close_code=close_code,
            reason=reason,
            duration_seconds=duration_seconds,
        )
    except Exception as exc:
        logger.warning("Failed to write websocket audit event '%s': %s", event_type, exc)

    audit_trail = _get_audit_trail(app)
    if audit_trail is None:
        return
    try:
        audit_trail.log_action(
            user_id=user_id,
            action=f"websocket.{event_type}",
            resource=task_id or "unknown-task",
            details={
                "message_size_bytes": message_size_bytes,
                "message_type": message_type,
                "close_code": close_code,
                "reason": reason,
                "duration_seconds": duration_seconds,
            },
            ip_address=None,
        )
    except Exception as exc:
        logger.warning("Failed to write general audit trail websocket event '%s': %s", event_type, exc)


def _extract_bearer_token(websocket: WebSocket) -> Optional[str]:
    token = websocket.query_params.get("token")
    if token:
        return token

    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()

    return None


def _sanitize_close_reason(reason: str) -> str:
    """
    RFC6455 limits reason payload to 123 bytes.
    """
    reason = reason.strip() if reason else ""
    if not reason:
        return "closed"
    encoded = reason.encode("utf-8")
    if len(encoded) <= 123:
        return reason
    return encoded[:123].decode("utf-8", errors="ignore")


async def _close_socket(
    websocket: WebSocket,
    state: _WebSocketConnectionState,
    *,
    code: int,
    reason: str,
) -> None:
    if state.closed:
        return
    state.closed = True
    state.close_code = code
    state.close_reason = reason
    try:
        await websocket.close(code=code, reason=_sanitize_close_reason(reason))
    except Exception:
        # Игнорируем ошибки закрытия: сокет мог быть уже закрыт клиентом.
        pass


def _message_size_bytes(text_payload: Optional[str], bytes_payload: Optional[bytes]) -> int:
    if bytes_payload is not None:
        return len(bytes_payload)
    if text_payload is None:
        return 0
    return len(text_payload.encode("utf-8"))


async def _send_json_with_audit(
    websocket: WebSocket,
    payload: dict,
    *,
    audit_storage: WebSocketAuditStorage,
    app,
    user_id: Optional[str],
    task_id: str,
    message_type: str,
) -> None:
    await websocket.send_json(payload)
    payload_size = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    _log_audit(
        audit_storage,
        app=app,
        event_type="message_sent",
        user_id=user_id,
        task_id=task_id,
        message_size_bytes=payload_size,
        message_type=message_type,
    )


def _mark_pong_if_present(
    *,
    state: _WebSocketConnectionState,
    text_payload: Optional[str],
    bytes_payload: Optional[bytes],
    now: float,
) -> str:
    """
    Returns inferred incoming message type for audit.
    """
    if bytes_payload is not None:
        if bytes_payload == b"pong":
            state.last_pong_monotonic = now
            return "pong"
        return "binary"

    if text_payload is None:
        return "text"

    normalized = text_payload.strip().lower()
    if normalized == "pong":
        state.last_pong_monotonic = now
        return "pong"

    try:
        parsed = json.loads(text_payload)
        if isinstance(parsed, dict) and str(parsed.get("type", "")).lower() == "pong":
            state.last_pong_monotonic = now
            return "pong"
    except json.JSONDecodeError:
        pass

    return "text"


async def _heartbeat_loop(
    websocket: WebSocket,
    *,
    state: _WebSocketConnectionState,
    settings: WebSocketRuntimeSettings,
    audit_storage: WebSocketAuditStorage,
    user_id: Optional[str],
    task_id: str,
) -> None:
    while not state.closed:
        await asyncio.sleep(settings.ping_interval_seconds)
        if state.closed:
            break

        now = time.monotonic()
        if now - state.last_pong_monotonic >= settings.ping_timeout_seconds:
            logger.warning(
                "WebSocket pong timeout: user_id=%s task_id=%s timeout=%ss",
                user_id,
                task_id,
                settings.ping_timeout_seconds,
            )
            _log_audit(
                audit_storage,
                app=websocket.app,
                event_type="pong_timeout",
                user_id=user_id,
                task_id=task_id,
                reason="Pong timeout",
            )
            await _close_socket(
                websocket,
                state,
                code=WS_CLOSE_NORMAL,
                reason="Pong timeout",
            )
            return

        ping_payload = {
            "type": "ping",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await _send_json_with_audit(
                websocket,
                ping_payload,
                audit_storage=audit_storage,
                app=websocket.app,
                user_id=user_id,
                task_id=task_id,
                message_type="ping",
            )
        except Exception:
            if not state.closed:
                await _close_socket(
                    websocket,
                    state,
                    code=WS_CLOSE_INTERNAL_ERROR,
                    reason="Internal server error",
                )
            return


async def _receive_loop(
    websocket: WebSocket,
    *,
    state: _WebSocketConnectionState,
    settings: WebSocketRuntimeSettings,
    audit_storage: WebSocketAuditStorage,
    user_id: Optional[str],
    task_id: str,
) -> None:
    while not state.closed:
        message = await websocket.receive()
        msg_type = message.get("type")

        if msg_type == "websocket.disconnect":
            state.closed = True
            state.close_code = message.get("code", WS_CLOSE_NORMAL)
            state.close_reason = "Client disconnected"
            return

        if msg_type != "websocket.receive":
            continue

        now = time.monotonic()
        window_start = now - 60
        while state.message_timestamps and state.message_timestamps[0] <= window_start:
            state.message_timestamps.popleft()

        if len(state.message_timestamps) >= settings.max_messages_per_minute:
            logger.warning(
                "WebSocket rate limit exceeded: user_id=%s task_id=%s limit=%s/min",
                user_id,
                task_id,
                settings.max_messages_per_minute,
            )
            _log_audit(
                audit_storage,
                app=websocket.app,
                event_type="rate_limit_exceeded",
                user_id=user_id,
                task_id=task_id,
                reason="Rate limit exceeded",
            )
            await _close_socket(
                websocket,
                state,
                code=WS_CLOSE_TRY_AGAIN_LATER,
                reason="Rate limit exceeded",
            )
            return

        state.message_timestamps.append(now)

        text_payload = message.get("text")
        bytes_payload = message.get("bytes")
        message_size = _message_size_bytes(text_payload, bytes_payload)
        incoming_type = _mark_pong_if_present(
            state=state,
            text_payload=text_payload,
            bytes_payload=bytes_payload,
            now=now,
        )

        if message_size > settings.max_message_size_bytes:
            logger.warning(
                "WebSocket message too big: user_id=%s task_id=%s size=%s limit=%s",
                user_id,
                task_id,
                message_size,
                settings.max_message_size_bytes,
            )
            _log_audit(
                audit_storage,
                app=websocket.app,
                event_type="message_too_big",
                user_id=user_id,
                task_id=task_id,
                message_size_bytes=message_size,
                message_type=incoming_type,
                reason="Message too big",
            )
            await _close_socket(
                websocket,
                state,
                code=WS_CLOSE_MESSAGE_TOO_BIG,
                reason="Message too big",
            )
            return

        _log_audit(
            audit_storage,
            app=websocket.app,
            event_type="message_received",
            user_id=user_id,
            task_id=task_id,
            message_size_bytes=message_size,
            message_type=incoming_type,
        )


@router.post("", response_model=TaskCreateResponse, status_code=201)
async def create_task(
    request: TaskCreateRequest,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Создаёт задачу и запускает выполнение в фоне."""
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    task_store[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "result": None,
        "error": None,
        "metadata": {
            "user": current_user.get("sub", "unknown"),
            **(request.metadata or {}),
        },
        "created_at": now,
        "updated_at": now,
    }

    asyncio.create_task(_run_task(task_id, request, orchestrator))

    return TaskCreateResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        status_endpoint=f"/api/v1/tasks/{task_id}",
        stream_endpoint=f"/ws/v1/tasks/{task_id}",
        created_at=now,
    )


async def _run_task(task_id: str, request: TaskCreateRequest, orchestrator):
    """Фоновое выполнение задачи."""
    task_store[task_id]["status"] = TaskStatus.IN_PROGRESS
    task_store[task_id]["updated_at"] = datetime.now(timezone.utc)
    try:
        result = await orchestrator.execute_task(
            task_id=task_id,
            prompt=request.prompt,
            task_type=request.task_type,
        )
        task_store[task_id]["status"] = TaskStatus.COMPLETED
        task_store[task_id]["result"] = result
    except Exception as e:
        task_store[task_id]["status"] = TaskStatus.FAILED
        task_store[task_id]["error"] = str(e)
    finally:
        task_store[task_id]["updated_at"] = datetime.now(timezone.utc)


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Возвращает статус и результат задачи."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskStatusResponse(**task)


@router.get("", response_model=list[TaskListItem])
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Список задач текущего пользователя."""
    user = current_user.get("sub", "")
    user_tasks = [
        TaskListItem(
            task_id=t["task_id"],
            status=t["status"],
            created_at=t["created_at"],
        )
        for t in task_store.values()
        if t.get("metadata", {}).get("user") == user
        or current_user.get("role") == "admin"
    ]
    user_tasks.sort(key=lambda x: x.created_at, reverse=True)
    return user_tasks[:limit]


@router.delete("/{task_id}", status_code=204)
async def cancel_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Отменяет задачу (помечает как FAILED)."""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if task["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        raise HTTPException(status_code=400, detail="Task already finished")
    task["status"] = TaskStatus.FAILED
    task["error"] = "Cancelled by user"
    task["updated_at"] = datetime.now(timezone.utc)


@router.websocket("/ws/{task_id}")
async def stream_task_result(websocket: WebSocket, task_id: str):
    """WebSocket для стриминга результата задачи с hardening-механизмами."""
    await websocket.accept()

    started_at = time.monotonic()
    state = _WebSocketConnectionState()
    settings = _get_runtime_settings(websocket)
    audit_storage = _get_audit_storage(websocket.app)
    user_id: Optional[str] = None

    token = _extract_bearer_token(websocket)
    payload = decode_access_token(token) if token else None
    if payload is None:
        await _close_socket(
            websocket,
            state,
            code=WS_CLOSE_POLICY_VIOLATION,
            reason="Invalid token",
        )
        _log_audit(
            audit_storage,
            app=websocket.app,
            event_type="close",
            user_id=None,
            task_id=task_id,
            close_code=state.close_code,
            reason=state.close_reason,
            duration_seconds=time.monotonic() - started_at,
        )
        return

    user_id = payload.get("sub", "unknown")
    _log_audit(
        audit_storage,
        app=websocket.app,
        event_type="connect",
        user_id=user_id,
        task_id=task_id,
    )

    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(
            websocket,
            state=state,
            settings=settings,
            audit_storage=audit_storage,
            user_id=user_id,
            task_id=task_id,
        )
    )
    receive_task = asyncio.create_task(
        _receive_loop(
            websocket,
            state=state,
            settings=settings,
            audit_storage=audit_storage,
            user_id=user_id,
            task_id=task_id,
        )
    )

    try:
        max_cycles = int(300 / settings.status_poll_interval_seconds)
        for _ in range(max_cycles):
            if state.closed:
                break

            task = task_store.get(task_id)
            if not task:
                await _close_socket(
                    websocket,
                    state,
                    code=WS_CLOSE_NORMAL,
                    reason="Task not found",
                )
                break

            if task["status"] == TaskStatus.COMPLETED:
                result = task.get("result", {})
                content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                await _send_json_with_audit(
                    websocket,
                    {"content": content, "done": True},
                    audit_storage=audit_storage,
                    app=websocket.app,
                    user_id=user_id,
                    task_id=task_id,
                    message_type="task_result",
                )
                await _close_socket(
                    websocket,
                    state,
                    code=WS_CLOSE_NORMAL,
                    reason="Task completed",
                )
                break
            if task["status"] == TaskStatus.FAILED:
                await _close_socket(
                    websocket,
                    state,
                    code=WS_CLOSE_INTERNAL_ERROR,
                    reason="Task failed",
                )
                break

            await _send_json_with_audit(
                websocket,
                {"content": None, "done": False},
                audit_storage=audit_storage,
                app=websocket.app,
                user_id=user_id,
                task_id=task_id,
                message_type="task_status",
            )
            await asyncio.sleep(settings.status_poll_interval_seconds)

        if not state.closed:
            await _close_socket(
                websocket,
                state,
                code=WS_CLOSE_NORMAL,
                reason="Stream timeout",
            )
    except WebSocketDisconnect:
        state.closed = True
        state.close_code = WS_CLOSE_NORMAL if state.close_code is None else state.close_code
        state.close_reason = state.close_reason or "Client disconnected"
    except Exception as exc:
        logger.exception("WebSocket internal error for task_id=%s: %s", task_id, exc)
        if not state.closed:
            await _close_socket(
                websocket,
                state,
                code=WS_CLOSE_INTERNAL_ERROR,
                reason="Internal server error",
            )
    finally:
        heartbeat_task.cancel()
        receive_task.cancel()
        await asyncio.gather(heartbeat_task, receive_task, return_exceptions=True)

        _log_audit(
            audit_storage,
            app=websocket.app,
            event_type="close",
            user_id=user_id,
            task_id=task_id,
            close_code=state.close_code,
            reason=state.close_reason,
            duration_seconds=time.monotonic() - started_at,
        )


@router.get("/ws/audit-log", response_model=list[WebSocketAuditLogEntry])
async def get_websocket_audit_log(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    task_id: Optional[str] = Query(default=None),
    user_id: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    """Возвращает audit log WebSocket-событий (только для admin)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    audit_storage = _get_audit_storage(request.app)
    rows = audit_storage.list_events(
        limit=limit,
        task_id=task_id,
        user_id=user_id,
        event_type=event_type,
    )
    return [WebSocketAuditLogEntry(**row) for row in rows]
