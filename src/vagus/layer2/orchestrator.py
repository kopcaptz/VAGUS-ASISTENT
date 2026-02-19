"""
Task Orchestrator — мозг системы.
State Machine: PENDING -> IN_PROGRESS -> COMPLETED
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from ..layer0.logging import get_logger


class TaskStatus(str, Enum):
    """Состояния задачи."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskOrchestrator:
    """
    Оркестратор задач: декомпозиция -> выполнение -> агрегация.
    Скелет для Дня 1. Полная реализация — Неделя 2+.
    """

    def __init__(
        self,
        communication: CommunicationLayer,
        agents: Optional[List[BaseAgent]] = None,
    ):
        """
        Args:
            communication: Слой коммуникации
            agents: Список агентов (Researcher, Coder, ...)
        """
        self.communication = communication
        self.agents = agents or []
        self.logger = get_logger("layer2.orchestrator")

    def register_agent(self, agent: BaseAgent) -> None:
        """Регистрирует агента."""
        self.agents.append(agent)
        self.logger.info(f"Agent registered: {agent.name}")

    async def execute_task(self, task_id: str, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """
        Выполняет задачу. Скелет — выбор агента и вызов process().
        """
        self.logger.info(f"Task {task_id}: {task_type} — PENDING")
        agent = self._select_agent(task_type)
        if not agent:
            return {"error": f"No agent for task_type={task_type}"}

        task = {"prompt": prompt, "task_type": task_type}
        try:
            result = await agent.process(task)
            await self.communication.publish_result(task_id, result)
            self.logger.info(f"Task {task_id}: COMPLETED")
            return result
        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            return {"error": str(e)}

    def _select_agent(self, task_type: str) -> Optional[BaseAgent]:
        """Выбирает агента по типу задачи. Пока — первый подходящий."""
        for agent in self.agents:
            if agent.can_handle(task_type):
                return agent
        return self.agents[0] if self.agents else None
