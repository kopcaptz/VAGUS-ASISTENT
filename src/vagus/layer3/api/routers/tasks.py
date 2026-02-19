"""
Роутер задач.
Эндпоинты: создание, статус, отмена задач. Взаимодействие с оркестратором.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from vagus.layer3.api.models import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatus,
    TaskStatusResponse,
)
from vagus.layer2.orchestrator import TaskOrchestrator

from ..dependencies import get_orchestrator, get_current_user, get_task_store

router = APIRouter(prefix="/tasks")


def _task_to_response(task_id: str, task: Dict[str, Any]) -> TaskStatusResponse:
    """Преобразует запись из task_store в TaskStatusResponse."""
    return TaskStatusResponse(
        task_id=task_id,
        status=TaskStatus(task["status"]),
        result=task.get("result"),
        error=task.get("error"),
        metadata=task.get("metadata") or {},
        created_at=task["created_at"],
        updated_at=task["updated_at"],
    )


@router.post("", response_model=TaskCreateResponse)
async def create_task(
    body: TaskCreateRequest,
    request: Request,
    orchestrator: TaskOrchestrator = Depends(get_orchestrator),
    _user: Any = Depends(get_current_user),
):
    """Создание задачи. Запускает выполнение в фоне."""
    task_id = str(uuid4())
    task_store = get_task_store(request)
    now = datetime.utcnow()

    task_store[task_id] = {
        "status": "pending",
        "prompt": body.prompt,
        "task_type": body.task_type,
        "result": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
        "metadata": body.metadata or {},
    }

    async def run_task():
        task_store[task_id]["status"] = "in_progress"
        task_store[task_id]["updated_at"] = datetime.utcnow()
        try:
            result = await orchestrator.execute_task(
                task_id=task_id,
                prompt=body.prompt,
                task_type=body.task_type,
            )
            if "error" in result:
                task_store[task_id]["status"] = "failed"
                task_store[task_id]["error"] = result["error"]
            else:
                task_store[task_id]["status"] = "completed"
                task_store[task_id]["result"] = result
        except Exception as e:
            task_store[task_id]["status"] = "failed"
            task_store[task_id]["error"] = str(e)
        task_store[task_id]["updated_at"] = datetime.utcnow()

    asyncio.create_task(run_task())

    base_url = str(request.base_url).rstrip("/")
    return TaskCreateResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        status_endpoint=f"{base_url}/api/v1/tasks/{task_id}",
        stream_endpoint=f"{base_url.replace('http', 'ws', 1)}/ws/tasks/{task_id}",
        created_at=now,
    )


@router.get("", response_model=list)
async def list_tasks(
    request: Request,
    limit: int = 10,
    _user: Any = Depends(get_current_user),
):
    """Список последних задач (по created_at)."""
    task_store = get_task_store(request)
    items = []
    for tid, task in task_store.items():
        resp = _task_to_response(tid, task)
        items.append({
            **resp.model_dump(),
            "prompt": task.get("prompt", ""),
        })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items[:limit]


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    request: Request,
    _user: Any = Depends(get_current_user),
):
    """Получение статуса задачи."""
    task_store = get_task_store(request)
    if task_id not in task_store:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_response(task_id, task_store[task_id])


@router.websocket("/{task_id}")
async def websocket_stream_task(
    websocket: WebSocket,
    task_id: str,
):
    """WebSocket стриминг результата задачи. Опрос каждые 0.5 сек."""
    await websocket.accept()
    app = websocket.scope["app"]
    task_store = app.state.task_store

    try:
        while True:
            if task_id not in task_store:
                await websocket.send_json({"error": "Task not found", "done": True})
                break

            task = task_store[task_id]
            status = task["status"]

            if status in ("completed", "failed"):
                if status == "completed":
                    result = task.get("result")
                    content = json.dumps(result) if isinstance(result, dict) else str(result)
                    await websocket.send_json({"content": content, "done": True})
                else:
                    await websocket.send_json({"error": task.get("error", "Unknown error"), "done": True})
                break

            await websocket.send_json({"content": None, "done": False})
            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
