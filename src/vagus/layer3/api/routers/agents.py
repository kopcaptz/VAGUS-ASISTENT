"""
Роутер агентов: информация о доступных агентах.
"""

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, get_orchestrator
from ..models import AgentInfoResponse

router = APIRouter(prefix="/agents", tags=["Agents"])

_AGENT_TASK_TYPES = {
    "researcher": ["research", "search", "find", "default"],
    "coder": ["code", "programming", "script", "python", "default"],
    "analyst": ["analysis", "statistics", "insights", "report", "default"],
}


@router.get("", response_model=list[AgentInfoResponse])
async def list_agents(
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Возвращает список зарегистрированных агентов."""
    agents_info = []
    for agent in orchestrator.agents:
        is_available = True
        health_checker = getattr(orchestrator, "is_agent_healthy", None)
        if callable(health_checker):
            try:
                is_available = bool(await health_checker(agent))
            except Exception:
                is_available = False
        agents_info.append(
            AgentInfoResponse(
                name=agent.name,
                description=agent.description or "",
                task_types=_AGENT_TASK_TYPES.get(agent.name, ["default"]),
                is_available=is_available,
            )
        )
    return agents_info
