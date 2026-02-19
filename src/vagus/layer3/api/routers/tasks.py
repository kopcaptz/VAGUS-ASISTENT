"""
Роутер задач: создание, статус, список, отмена, WebSocket-стриминг.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from ..dependencies import get_current_user, get_orchestrator
from ..models import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskListResponse,
    TaskStatus,
    TaskStatusResponse,
)

router = APIRouter(prefix="/tasks", tags=["Tasks"])

_task_store: dict[str, dict] = {}


@router.post("", response_model=TaskCreateResponse, status_code=201)
async def create_task(
    request: TaskCreateRequest,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Creates a new task and launches background execution."""
    task_id = str(uuid.uuid4())
    now = datetime.utcnow()

    _task_store[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "result": None,
        "error": None,
        "metadata": {"user_id": current_user.get("sub", "unknown")},
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


async def _run_task(task_id: str, request: TaskCreateRequest, orchestrator) -> None:
    """Background coroutine that executes the task via the orchestrator."""
    _task_store[task_id]["status"] = TaskStatus.IN_PROGRESS
    _task_store[task_id]["updated_at"] = datetime.utcnow()
    try:
        result = await orchestrator.execute_task(
            task_id=task_id,
            prompt=request.prompt,
            task_type=request.task_type,
        )
        _task_store[task_id]["status"] = TaskStatus.COMPLETED
        _task_store[task_id]["result"] = result
    except Exception as e:
        _task_store[task_id]["status"] = TaskStatus.FAILED
        _task_store[task_id]["error"] = str(e)
    finally:
        _task_store[task_id]["updated_at"] = datetime.utcnow()


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Returns current status and result of a task."""
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskStatusResponse(**task)


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Returns a paginated list of tasks for the current user."""
    user_id = current_user.get("sub", "unknown")
    all_tasks = sorted(
        _task_store.values(),
        key=lambda t: t["created_at"],
        reverse=True,
    )
    user_tasks = [
        t for t in all_tasks if t.get("metadata", {}).get("user_id") == user_id
    ]
    page = user_tasks[offset : offset + limit]
    return TaskListResponse(
        tasks=[TaskStatusResponse(**t) for t in page],
        total=len(user_tasks),
    )


@router.delete("/{task_id}", status_code=204)
async def cancel_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Cancels a task if it is still pending or in progress."""
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    if task["status"] in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        raise HTTPException(status_code=409, detail="Task already finished")
    task["status"] = TaskStatus.FAILED
    task["error"] = "Cancelled by user"
    task["updated_at"] = datetime.utcnow()


def get_task_store() -> dict[str, dict]:
    """Exposes task store for WebSocket router and testing."""
    return _task_store
