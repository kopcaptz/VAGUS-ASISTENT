"""
Task Orchestrator — мозг системы.
State Machine: PENDING -> IN_PROGRESS -> COMPLETED
"""

import asyncio
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from ..layer0.logging import get_logger

if TYPE_CHECKING:
    from .memory.episodic import EpisodicMemory
    from .memory.semantic import SemanticMemory


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
        semantic_memory: Optional["SemanticMemory"] = None,
    ):
        """
        Args:
            communication: Слой коммуникации
            agents: Список агентов (Researcher, Coder, ...)
            memory: EpisodicMemory для записи истории выполнения (опционально)
            semantic_memory: SemanticMemory для векторного поиска похожих задач (опционально)
        """
        self.communication = communication
        self.agents = agents or []
        self.memory = memory
        self.semantic_memory = semantic_memory
        self.logger = get_logger("layer2.orchestrator")

    def register_agent(self, agent: BaseAgent) -> None:
        """Регистрирует агента."""
        self.agents.append(agent)
        self.logger.info(f"Agent registered: {agent.name}")

    async def execute_task(self, task_id: str, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """
        Выполняет задачу. Скелет — выбор агента и вызов process().
        Записывает шаги в EpisodicMemory при наличии.
        При наличии SemanticMemory: ищет похожие задачи и добавляет контекст.
        """
        self.logger.info(f"Task {task_id}: {task_type} — PENDING")
        agent = self._select_agent(task_type)
        if not agent:
            return {"error": f"No agent for task_type={task_type}"}

        # Поиск похожих задач и извлечение контекста
        context_prefix = ""
        if self.semantic_memory:
            context_prefix = self.semantic_memory.get_context(prompt, top_k=2)
            if context_prefix:
                context_prefix = (
                    "Релевантный контекст из похожих выполненных задач:\n"
                    f"{context_prefix}\n\n---\nИсходный запрос: "
                )

        enhanced_prompt = f"{context_prefix}{prompt}" if context_prefix else prompt
        task = {"task_id": task_id, "prompt": enhanced_prompt, "task_type": task_type}

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
            # Синхронизация в SemanticMemory для будущего поиска похожих
            if self.semantic_memory and self.memory:
                from .memory.semantic import sync_episodic_to_semantic
                sync_episodic_to_semantic(
                    self.memory, self.semantic_memory,
                    task_id=task_id, prompt=prompt, task_type=task_type,
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

    async def execute_parallel_tasks(
        self,
        task_ids: List[str],
        prompts: List[str],
        task_types: Optional[List[str]] = None,
        max_concurrency: int = 5,
    ) -> Dict[str, Any]:
        """
        Параллельное выполнение независимых задач.
        Использует asyncio.gather() с ограничением через Semaphore.

        Args:
            task_ids: Список идентификаторов задач
            prompts: Список промптов (должен совпадать по длине с task_ids)
            task_types: Список типов задач (по умолчанию "default" для всех)
            max_concurrency: Максимум одновременных задач (semaphore)

        Returns:
            Dict с results (по task_id), errors, completed_count
        """
        if len(task_ids) != len(prompts):
            return {
                "error": "task_ids and prompts length mismatch",
                "results": {},
                "errors": {},
                "completed_count": 0,
            }
        task_types = task_types or ["default"] * len(task_ids)
        if len(task_types) != len(task_ids):
            task_types = task_types + ["default"] * (len(task_ids) - len(task_types))

        semaphore = asyncio.Semaphore(max_concurrency)

        async def _run_one(tid: str, prompt: str, ttype: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.execute_task(tid, prompt, ttype)

        self.logger.info(f"Parallel execution: {len(task_ids)} tasks, max_concurrency={max_concurrency}")
        coros = [_run_one(tid, p, t) for tid, p, t in zip(task_ids, prompts, task_types)]
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        for task_id, raw in zip(task_ids, raw_results):
            if isinstance(raw, Exception):
                errors[task_id] = str(raw)
                results[task_id] = {"error": str(raw)}
            else:
                results[task_id] = raw
                if "error" in raw and raw.get("error"):
                    errors[task_id] = str(raw["error"])

        return {
            "results": results,
            "errors": errors,
            "completed_count": len(task_ids) - len(errors),
            "total_count": len(task_ids),
        }

    def _select_agent(self, task_type: str) -> Optional[BaseAgent]:
        """Выбирает агента по типу задачи. Пока — первый подходящий."""
        for agent in self.agents:
            if agent.can_handle(task_type):
                return agent
        return self.agents[0] if self.agents else None
