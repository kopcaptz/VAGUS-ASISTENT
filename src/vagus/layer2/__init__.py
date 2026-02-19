"""
Слой 2: Агентная система — Orchestrator-Worker.
"""

from typing import Any

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from .agents.analyst import AnalystAgent
from .agents.coder import CoderAgent
from .agents.researcher import ResearcherAgent
from .memory import EpisodicMemory
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


def create_orchestrator_full(llm_router: Any) -> TaskOrchestrator:
    """
    Создаёт TaskOrchestrator со всеми агентами (Researcher, Coder, Analyst)
    и EpisodicMemory. Для многошаговых задач и E2E.
    """
    communication = CommunicationLayer()
    memory = EpisodicMemory()
    skill_system = SkillSystem()
    orchestrator = TaskOrchestrator(communication=communication, memory=memory)
    orchestrator.register_agent(ResearcherAgent(llm_router=llm_router, skill_system=skill_system))
    orchestrator.register_agent(CoderAgent(llm_router=llm_router, skill_system=skill_system))
    orchestrator.register_agent(AnalystAgent(llm_router=llm_router))
    return orchestrator


__all__ = [
    "AnalystAgent",
    "CommunicationLayer",
    "BaseAgent",
    "CoderAgent",
    "EpisodicMemory",
    "ResearcherAgent",
    "TaskOrchestrator",
    "SkillSystem",
    "create_orchestrator_full",
    "create_orchestrator_with_researcher",
]
