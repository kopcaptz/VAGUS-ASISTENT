"""
Слой 2: Агентная система — Orchestrator-Worker.
"""

from typing import Any, Optional

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from .agents.analyst import AnalystAgent
from .agents.coder import CoderAgent
from .agents.researcher import ResearcherAgent
from .dead_letter_queue import DeadLetterQueueStorage
from .memory import EpisodicMemory, SemanticMemory
from .orchestrator import TaskOrchestrator
from .skills import SkillSystem


def create_orchestrator_with_researcher(
    llm_router: Any,
    *,
    dead_letter_queue: Optional[DeadLetterQueueStorage] = None,
    task_timeouts: Optional[dict[str, float]] = None,
    cluster_config: Optional[dict[str, Any]] = None,
) -> TaskOrchestrator:
    """
    Создаёт TaskOrchestrator с зарегистрированным ResearcherAgent.
    Удобная точка входа для E2E и первого сценария.
    """
    communication = CommunicationLayer()
    skill_system = SkillSystem()
    researcher = ResearcherAgent(llm_router=llm_router, skill_system=skill_system)
    orchestrator = TaskOrchestrator(
        communication=communication,
        dead_letter_queue=dead_letter_queue,
        task_timeouts=task_timeouts,
        skill_system=skill_system,
        cluster_config=cluster_config,
    )
    orchestrator.register_agent(researcher)
    return orchestrator


def create_orchestrator_full(
    llm_router: Any,
    *,
    dead_letter_queue: Optional[DeadLetterQueueStorage] = None,
    task_timeouts: Optional[dict[str, float]] = None,
    error_analytics: Optional[Any] = None,
    cluster_config: Optional[dict[str, Any]] = None,
) -> TaskOrchestrator:
    """
    Создаёт TaskOrchestrator со всеми агентами (Researcher, Coder, Analyst),
    EpisodicMemory и SemanticMemory для векторного поиска похожих задач.
    """
    communication = CommunicationLayer()
    memory = EpisodicMemory()
    semantic_memory = SemanticMemory()
    skill_system = SkillSystem()
    orchestrator = TaskOrchestrator(
        communication=communication,
        memory=memory,
        semantic_memory=semantic_memory,
        dead_letter_queue=dead_letter_queue,
        task_timeouts=task_timeouts,
        skill_system=skill_system,
        error_analytics=error_analytics,
        cluster_config=cluster_config,
    )
    orchestrator.register_agent(ResearcherAgent(llm_router=llm_router, skill_system=skill_system))
    orchestrator.register_agent(CoderAgent(llm_router=llm_router, skill_system=skill_system))
    orchestrator.register_agent(AnalystAgent(llm_router=llm_router))
    return orchestrator


__all__ = [
    "AnalystAgent",
    "CommunicationLayer",
    "BaseAgent",
    "CoderAgent",
    "DeadLetterQueueStorage",
    "EpisodicMemory",
    "ResearcherAgent",
    "SemanticMemory",
    "TaskOrchestrator",
    "SkillSystem",
    "create_orchestrator_full",
    "create_orchestrator_with_researcher",
]
