"""
WebSocket роутер для real-time событий задач из Redis Streams.
"""

from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vagus.layer0.logging import get_logger
from vagus.layer2.communication.redis_streams import DEFAULT_STREAM_NAME

from ..auth import decode_access_token
from ..websockets import TaskEventsWebSocket

logger = get_logger("layer3.api.websocket_events")

router = APIRouter(prefix="/ws", tags=["WebSocket Events"])

WS_CLOSE_POLICY_VIOLATION = 1008
WS_CLOSE_SERVICE_UNAVAILABLE = 1011


def _extract_bearer_token(websocket: WebSocket) -> Optional[str]:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


@router.websocket("/tasks/{task_id}")
async def task_events_websocket(websocket: WebSocket, task_id: str) -> None:
    """
    WebSocket для real-time трансляции событий задачи из Redis Streams.
    События: task.planned, quality_gate.passed, agent.started (reflection.triggered).
    Требует Bearer token в query ?token=... или Authorization header.
    """
    await websocket.accept()

    token = _extract_bearer_token(websocket)
    payload = decode_access_token(token) if token else None
    if payload is None:
        await websocket.close(code=WS_CLOSE_POLICY_VIOLATION, reason="Invalid token")
        return

    app = websocket.app
    orchestrator = getattr(app.state, "orchestrator", None)
    if not orchestrator:
        await websocket.close(
            code=WS_CLOSE_SERVICE_UNAVAILABLE,
            reason="Orchestrator not available",
        )
        return

    event_bus = getattr(orchestrator, "event_bus", None)
    if not event_bus or not getattr(event_bus, "uses_streams", False):
        await websocket.close(
            code=WS_CLOSE_SERVICE_UNAVAILABLE,
            reason="Redis Streams not enabled",
        )
        return

    streams_client = getattr(event_bus, "_streams_client", None)
    if not streams_client:
        await websocket.close(
            code=WS_CLOSE_SERVICE_UNAVAILABLE,
            reason="Redis Streams not configured",
        )
        return

    stream_name = getattr(event_bus, "_stream_name", None) or DEFAULT_STREAM_NAME

    handler = TaskEventsWebSocket(
        websocket=websocket,
        task_id=task_id,
        redis_streams_client=streams_client,
        stream_name=stream_name,
    )

    try:
        await handler.run()
    except WebSocketDisconnect:
        logger.debug("Task events WebSocket disconnected: task_id=%s", task_id)
    except Exception as exc:
        logger.warning("Task events WebSocket error for task_id=%s: %s", task_id, exc)
        try:
            await websocket.close(code=WS_CLOSE_SERVICE_UNAVAILABLE, reason="Internal error")
        except Exception:
            pass
