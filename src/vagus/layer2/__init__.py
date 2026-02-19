"""
Слой 2: Агентная система — Orchestrator-Worker.
"""

from typing import Any

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from .agents.researcher import ResearcherAgent
from .orchestrator import TaskOrchestrator
from .skills import SkillSystem


def create_orchestrator_with_researcher(llm_router: Any) -> TaskOrchestrator:
    """
    Создаёт TaskOrchestrator с зарегистрированным ResearcherAgent.
    Удобная точка входа для E2E и первого сценария.
    """
    communication = CommunicationLayer()
    skill_system = SkillSystem()
    researcher = ResearcherAgent(llm_router=llm_router, skill_system=skill_system)
    orchestrator = TaskOrchestrator(communication=communication)
    orchestrator.register_agent(researcher)
    return orchestrator


__all__ = [
    "CommunicationLayer",
    "BaseAgent",
    "ResearcherAgent",
    "TaskOrchestrator",
    "SkillSystem",
    "create_orchestrator_with_researcher",
]
