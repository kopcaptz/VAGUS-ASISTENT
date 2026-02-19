"""
Роутер агентов: получение информации о доступных агентах.
"""

from typing import List

from fastapi import APIRouter, Depends

from ..dependencies import get_current_user, get_orchestrator
from ..models import AgentInfoResponse

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=List[AgentInfoResponse])
async def list_agents(
    orchestrator=Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Returns list of registered agents and their capabilities."""
    agents_info = []
    for agent in orchestrator.agents:
        task_types = []
        if hasattr(agent, "TASK_TYPES"):
            task_types = list(agent.TASK_TYPES)
        agents_info.append(
            AgentInfoResponse(
                name=agent.name,
                description=getattr(agent, "description", ""),
                task_types=task_types,
                is_available=True,
            )
        )
    return agents_info
