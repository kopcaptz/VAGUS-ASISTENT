"""
Роутер статуса системы.
"""

import time

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_current_user, get_orchestrator
from ..models import SystemStatusResponse, TaskStatus
from .tasks import task_store

router = APIRouter(prefix="/status", tags=["System Status"])


@router.get("", response_model=SystemStatusResponse)
async def get_system_status(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Возвращает общее состояние системы."""
    start_time = getattr(request.app.state, "start_time", time.monotonic())
    llm_router = getattr(request.app.state, "llm_router", None)

    layer1_stats = {}
    if llm_router is not None:
        try:
            layer1_stats = llm_router.get_stats()
        except Exception:
            pass

    active = sum(
        1
        for t in task_store.values()
        if t["status"] in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
    )

    return SystemStatusResponse(
        layer1_stats=layer1_stats,
        layer2_agents_count=len(orchestrator.agents),
        active_tasks_count=active,
        uptime_seconds=time.monotonic() - start_time,
    )
