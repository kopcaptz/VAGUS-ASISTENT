"""
Task Orchestrator — мозг системы.
State Machine: PENDING -> IN_PROGRESS -> COMPLETED
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from ..layer0.logging import get_logger

if TYPE_CHECKING:
    from .memory.episodic import EpisodicMemory


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
        memory: Optional["EpisodicMemory"] = None,
    ):
        """
        Args:
            communication: Слой коммуникации
            agents: Список агентов (Researcher, Coder, ...)
            memory: EpisodicMemory для записи истории выполнения (опционально)
        """
        self.communication = communication
        self.agents = agents or []
        self.memory = memory
        self.logger = get_logger("layer2.orchestrator")

    def register_agent(self, agent: BaseAgent) -> None:
        """Регистрирует агента."""
        self.agents.append(agent)
        self.logger.info(f"Agent registered: {agent.name}")

    async def execute_task(self, task_id: str, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """
        Выполняет задачу. Скелет — выбор агента и вызов process().
        Записывает шаги в EpisodicMemory при наличии.
        """
        self.logger.info(f"Task {task_id}: {task_type} — PENDING")
        agent = self._select_agent(task_type)
        if not agent:
            return {"error": f"No agent for task_type={task_type}"}

        task = {"task_id": task_id, "prompt": prompt, "task_type": task_type}
        try:
            result = await agent.process(task)
            if self.memory:
                self.memory.add_step(
                    task_id,
                    agent.name,
                    "process",
                    result,
                    metadata={"task_type": task_type, "prompt": prompt[:100]},
                )
            await self.communication.publish_result(task_id, result)
            self.logger.info(f"Task {task_id}: COMPLETED")
            return result
        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            if self.memory:
                self.memory.add_step(
                    task_id,
                    agent.name,
                    "process",
                    {"error": str(e)},
                    metadata={"task_type": task_type, "failed": True},
                )
            return {"error": str(e)}

    async def execute_multi_step_task(
        self,
        task_id: str,
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Выполняет многошаговую задачу (цепочку шагов).
        Каждый шаг: {"type": "research"|"code"|"analysis", "prompt": "..."}
        Результаты предыдущих шагов передаются в контекст следующим.
        Записывает каждый шаг в EpisodicMemory.
        """
        if not steps:
            return {"error": "Empty steps", "steps_results": []}

        self.logger.info(f"Multi-step task {task_id}: {len(steps)} steps")
        steps_results: List[Dict[str, Any]] = []
        context: Dict[str, Any] = {"previous_steps": []}

        for i, step_def in enumerate(steps):
            step_type = step_def.get("type", "default")
            prompt = step_def.get("prompt", "").strip()
            step_task_id = f"{task_id}_step_{i}"

            agent = self._select_agent(step_type)
            if not agent:
                err = {"error": f"No agent for type={step_type}", "step_index": i}
                steps_results.append(err)
                if self.memory:
                    self.memory.add_step(
                        task_id,
                        "orchestrator",
                        "multi_step",
                        err,
                        metadata={"step_index": i, "step_type": step_type, "failed": True},
                    )
                return {
                    "error": f"No agent for step type={step_type}",
                    "steps_results": steps_results,
                }

            task = {
                "task_id": step_task_id,
                "prompt": prompt,
                "task_type": step_type,
            }

            try:
                result = await agent.process(task, context=context)
                steps_results.append(result)

                if self.memory:
                    self.memory.add_step(
                        task_id,
                        agent.name,
                        "process",
                        result,
                        metadata={
                            "step_index": i,
                            "step_type": step_type,
                            "prompt": prompt[:100],
                        },
                    )

                # Агрегация: добавляем результат в контекст для следующих шагов
                context["previous_steps"].append(
                    {"content": result.get("content", ""), "result": result}
                )

            except Exception as e:
                self.logger.error(f"Step {i} failed: {e}")
                err_result = {"error": str(e), "step_index": i}
                steps_results.append(err_result)
                if self.memory:
                    self.memory.add_step(
                        task_id,
                        agent.name,
                        "process",
                        err_result,
                        metadata={"step_index": i, "step_type": step_type, "failed": True},
                    )
                return {
                    "error": str(e),
                    "steps_results": steps_results,
                }

        # Агрегированный результат
        return {
            "steps_results": steps_results,
            "step_count": len(steps_results),
            "context": context,
        }

    def _select_agent(self, task_type: str) -> Optional[BaseAgent]:
        """Выбирает агента по типу задачи. Пока — первый подходящий."""
        for agent in self.agents:
            if agent.can_handle(task_type):
                return agent
        return self.agents[0] if self.agents else None
