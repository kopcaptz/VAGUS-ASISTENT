"""
Роутер задач: CRUD + WebSocket стриминг.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..auth import decode_access_token
from ..dependencies import get_current_user, get_orchestrator
from ..models import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskListItem,
    TaskStatus,
    TaskStatusResponse,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])

task_store: Dict[str, dict] = {}


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
        stream_endpoint=f"/api/v1/tasks/ws/{task_id}",
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
    """WebSocket для стриминга результата задачи."""
    token = websocket.query_params.get("token")
    user = decode_access_token(token) if token else None

    await websocket.accept()
    if user is None:
        await websocket.send_json({"error": "Unauthorized", "done": True})
        await websocket.close(code=1008)
        return

    try:
        for _ in range(600):  # max 5 min
            task = task_store.get(task_id)
            if not task:
                await websocket.send_json({"error": "Task not found", "done": True})
                break
            owner = task.get("metadata", {}).get("user")
            if owner and user.get("role") != "admin" and user.get("sub") != owner:
                await websocket.send_json({"error": "Forbidden", "done": True})
                break
            if task["status"] == TaskStatus.COMPLETED:
                result = task.get("result", {})
                content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                await websocket.send_json({"content": content, "done": True})
                break
            elif task["status"] == TaskStatus.FAILED:
                await websocket.send_json(
                    {"error": task.get("error", "Unknown error"), "done": True}
                )
                break
            else:
                await websocket.send_json({"content": None, "done": False})
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
