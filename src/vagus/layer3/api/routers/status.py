"""
Роутер статуса системы: метрики, здоровье, uptime.
"""

import time

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_current_user, get_orchestrator
from ..models import SystemStatusResponse, TaskStatus
from .tasks import get_task_store

router = APIRouter(prefix="/status", tags=["Status"])


@router.get("", response_model=SystemStatusResponse)
async def get_system_status(
    request: Request,
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Returns overall system health and metrics."""
    llm_router = getattr(request.app.state, "llm_router", None)
    layer1_stats = {}
    if llm_router and hasattr(llm_router, "get_stats"):
        layer1_stats = llm_router.get_stats()

    task_store = get_task_store()
    active_count = sum(
        1 for t in task_store.values()
        if t.get("status") in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
    )

    start_time = getattr(request.app.state, "start_time", time.monotonic())
    uptime = time.monotonic() - start_time

    return SystemStatusResponse(
        layer1_stats=layer1_stats,
        layer2_agents_count=len(orchestrator.agents),
        active_tasks_count=active_count,
        uptime_seconds=round(uptime, 2),
    )
