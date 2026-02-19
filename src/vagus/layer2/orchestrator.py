"""
Task Orchestrator — мозг системы.
State Machine: PENDING -> IN_PROGRESS -> COMPLETED
"""

import asyncio
import json
import traceback
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .communication import CommunicationLayer
from .agents.base_agent import BaseAgent
from .dead_letter_queue import DeadLetterQueueStorage
from .skills import SkillSystem
from ..layer0.logging import get_logger

if TYPE_CHECKING:
    from .memory.episodic import EpisodicMemory
    from .memory.semantic import SemanticMemory
    from ..monitoring.error_analytics import ErrorAnalyticsStorage


class _InMemorySharedTaskQueue:
    """In-process fallback queue for task distribution."""

    def __init__(self):
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def enqueue(self, payload: dict[str, Any]) -> None:
        await self._queue.put(payload)

    async def dequeue(self, timeout_seconds: float = 1.0) -> Optional[dict[str, Any]]:
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=max(0.1, timeout_seconds))
        except asyncio.TimeoutError:
            return None

    def get_stats(self) -> dict[str, Any]:
        return {"backend": "memory", "queue_size": self._queue.qsize()}


class _RedisSharedTaskQueue:
    """Redis-backed shared queue for horizontal scaling."""

    def __init__(self, redis_url: str, queue_name: str):
        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("redis package is not available") from exc
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._queue_name = queue_name
        self._redis_url = redis_url

    async def enqueue(self, payload: dict[str, Any]) -> None:
        await self._redis.rpush(self._queue_name, json.dumps(payload, ensure_ascii=False, default=str))

    async def dequeue(self, timeout_seconds: float = 1.0) -> Optional[dict[str, Any]]:
        timeout = max(1, int(timeout_seconds))
        item = await self._redis.blpop(self._queue_name, timeout=timeout)
        if not item:
            return None
        _, raw_payload = item
        try:
            decoded = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {"raw_payload": raw_payload}
        return decoded if isinstance(decoded, dict) else {"payload": decoded}

    def get_stats(self) -> dict[str, Any]:
        return {"backend": "redis", "queue_name": self._queue_name, "redis_url": self._redis_url}


class _RedisDistributedLock:
    """Simple distributed lock using Redis SET NX EX."""

    def __init__(self, redis_url: str, *, lock_prefix: str = "vagus:lock"):
        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("redis package is not available") from exc
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._lock_prefix = lock_prefix
        self._owned_tokens: dict[str, str] = {}
        self._redis_url = redis_url

    def _key(self, resource_id: str) -> str:
        return f"{self._lock_prefix}:{resource_id}"

    async def acquire(self, resource_id: str, ttl_seconds: int) -> bool:
        lock_key = self._key(resource_id)
        token = str(uuid.uuid4())
        acquired = await self._redis.set(lock_key, token, nx=True, ex=max(1, int(ttl_seconds)))
        if acquired:
            self._owned_tokens[resource_id] = token
            return True
        return False

    async def release(self, resource_id: str) -> bool:
        lock_key = self._key(resource_id)
        token = self._owned_tokens.get(resource_id)
        if not token:
            return False
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self._redis.eval(script, 1, lock_key, token)
        self._owned_tokens.pop(resource_id, None)
        return bool(result)

    def get_stats(self) -> dict[str, Any]:
        return {
            "backend": "redis",
            "redis_url": self._redis_url,
            "owned_locks": len(self._owned_tokens),
        }


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
        dead_letter_queue: Optional[DeadLetterQueueStorage] = None,
        task_timeouts: Optional[Dict[str, float]] = None,
        skill_system: Optional[SkillSystem] = None,
        error_analytics: Optional["ErrorAnalyticsStorage"] = None,
        cluster_config: Optional[Dict[str, Any]] = None,
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
        self.dead_letter_queue = dead_letter_queue or DeadLetterQueueStorage()
        self.skill_system = skill_system or SkillSystem()
        self.error_analytics = error_analytics
        self.logger = get_logger("layer2.orchestrator")
        self.task_timeouts = self._normalize_task_timeouts(task_timeouts)
        self.cluster_config = self._normalize_cluster_config(cluster_config)
        self.node_id = str(self.cluster_config.get("node_id"))
        self.stateless_agents = bool(self.cluster_config.get("stateless_agents", True))
        self._shared_task_queue = self._init_shared_task_queue(self.cluster_config)
        self._distributed_lock = self._init_distributed_lock(self.cluster_config)
        self.logger.info(
            "Orchestrator scalability: node_id=%s stateless=%s queue=%s lock=%s",
            self.node_id,
            self.stateless_agents,
            self._shared_task_queue.get_stats().get("backend"),
            (
                self._distributed_lock.get_stats().get("backend")
                if self._distributed_lock is not None
                else "disabled"
            ),
        )

    @staticmethod
    def _normalize_cluster_config(cluster_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "enabled": False,
            "node_id": "node-local",
            "stateless_agents": True,
            "shared_task_queue": {
                "enabled": False,
                "redis_url": None,
                "queue_name": "vagus:cluster:tasks",
            },
            "distributed_locking": {
                "enabled": False,
                "redis_url": None,
                "lock_ttl_seconds": 900,
            },
        }
        if not isinstance(cluster_config, dict):
            return defaults

        normalized = dict(defaults)
        normalized.update(
            {
                "enabled": bool(cluster_config.get("enabled", defaults["enabled"])),
                "node_id": str(cluster_config.get("node_id", defaults["node_id"])),
                "stateless_agents": bool(
                    cluster_config.get("stateless_agents", defaults["stateless_agents"])
                ),
            }
        )

        queue_cfg = cluster_config.get("shared_task_queue", {})
        if isinstance(queue_cfg, dict):
            merged_queue_cfg = dict(defaults["shared_task_queue"])
            merged_queue_cfg.update(queue_cfg)
            normalized["shared_task_queue"] = merged_queue_cfg

        lock_cfg = cluster_config.get("distributed_locking", {})
        if isinstance(lock_cfg, dict):
            merged_lock_cfg = dict(defaults["distributed_locking"])
            merged_lock_cfg.update(lock_cfg)
            normalized["distributed_locking"] = merged_lock_cfg
        return normalized

    def _init_shared_task_queue(self, cluster_config: Dict[str, Any]):
        queue_cfg = cluster_config.get("shared_task_queue", {})
        if not isinstance(queue_cfg, dict):
            return _InMemorySharedTaskQueue()
        if not bool(queue_cfg.get("enabled", False)):
            return _InMemorySharedTaskQueue()
        redis_url = queue_cfg.get("redis_url")
        queue_name = str(queue_cfg.get("queue_name", "vagus:cluster:tasks"))
        if not redis_url:
            self.logger.warning("Shared queue enabled without redis_url; fallback to in-memory queue")
            return _InMemorySharedTaskQueue()
        try:
            return _RedisSharedTaskQueue(str(redis_url), queue_name)
        except Exception as exc:
            self.logger.warning("Failed to initialize Redis shared queue, fallback to memory: %s", exc)
            return _InMemorySharedTaskQueue()

    def _init_distributed_lock(self, cluster_config: Dict[str, Any]):
        lock_cfg = cluster_config.get("distributed_locking", {})
        if not isinstance(lock_cfg, dict) or not bool(lock_cfg.get("enabled", False)):
            return None
        redis_url = lock_cfg.get("redis_url")
        if not redis_url:
            self.logger.warning("Distributed locking enabled without redis_url; locking disabled")
            return None
        try:
            return _RedisDistributedLock(str(redis_url))
        except Exception as exc:
            self.logger.warning("Failed to initialize Redis distributed lock: %s", exc)
            return None

    def get_scalability_stats(self) -> Dict[str, Any]:
        lock_stats = self._distributed_lock.get_stats() if self._distributed_lock is not None else {
            "backend": "disabled"
        }
        return {
            "cluster_enabled": bool(self.cluster_config.get("enabled", False)),
            "node_id": self.node_id,
            "stateless_agents": self.stateless_agents,
            "shared_task_queue": self._shared_task_queue.get_stats(),
            "distributed_locking": lock_stats,
        }

    async def enqueue_task_for_cluster(self, payload: Dict[str, Any]) -> None:
        """Публикует задачу в shared queue для горизонтального scaling."""
        if not isinstance(payload, dict):
            raise ValueError("payload must be a dict")
        await self._shared_task_queue.enqueue(payload)

    async def dequeue_task_for_cluster(self, timeout_seconds: float = 1.0) -> Optional[Dict[str, Any]]:
        """Забирает задачу из shared queue для обработки текущим node."""
        return await self._shared_task_queue.dequeue(timeout_seconds=timeout_seconds)

    async def _execute_with_distributed_lock(
        self,
        *,
        task_id: str,
        timeout_seconds: float,
        coroutine_factory,
    ):
        if self._distributed_lock is None:
            return await coroutine_factory()

        lock_cfg = self.cluster_config.get("distributed_locking", {})
        lock_ttl_seconds = int(lock_cfg.get("lock_ttl_seconds", 900))
        lock_ttl_seconds = max(lock_ttl_seconds, int(timeout_seconds) + 30)

        acquired = await self._distributed_lock.acquire(task_id, lock_ttl_seconds)
        if not acquired:
            raise RuntimeError(f"Task {task_id} is already being processed by another node")
        try:
            return await coroutine_factory()
        finally:
            await self._distributed_lock.release(task_id)

    @staticmethod
    def _normalize_task_timeouts(
        task_timeouts: Optional[Dict[str, float]],
    ) -> Dict[str, float]:
        defaults: Dict[str, float] = {
            "researcher": 300.0,
            "coder": 600.0,
            "analyst": 180.0,
        }
        if not isinstance(task_timeouts, dict):
            return defaults
        normalized = dict(defaults)
        for key in ("researcher", "coder", "analyst"):
            value = task_timeouts.get(key)
            if value is None:
                continue
            try:
                parsed = float(value)
                if parsed > 0:
                    normalized[key] = parsed
            except (TypeError, ValueError):
                continue
        return normalized

    def register_agent(self, agent: BaseAgent) -> None:
        """Регистрирует агента."""
        self.agents.append(agent)
        self.logger.info(f"Agent registered: {agent.name}")

    async def is_agent_healthy(self, agent: BaseAgent) -> bool:
        """Проверяет доступность агента перед назначением задачи."""
        checker = getattr(agent, "is_available", None)
        if not callable(checker):
            return True
        try:
            value = checker()
            if asyncio.iscoroutine(value):
                value = await value
            return bool(value)
        except Exception as exc:
            self.logger.warning("Health check failed for agent %s: %s", agent.name, exc)
            return False

    def _normalize_task_category(self, task_type: str) -> str:
        task_lower = (task_type or "").lower()
        if any(x in task_lower for x in ("research", "search", "find", "узнай", "найди")):
            return "researcher"
        if any(x in task_lower for x in ("code", "programming", "script", "python", "код")):
            return "coder"
        if any(
            x in task_lower
            for x in ("analysis", "statistics", "insights", "report", "анализ", "отчёт")
        ):
            return "analyst"
        return "default"

    def _resolve_timeout_seconds(self, *, task_type: str, agent: BaseAgent) -> float:
        agent_key = (getattr(agent, "name", "") or "").lower()
        if agent_key in self.task_timeouts:
            return float(self.task_timeouts[agent_key])
        task_key = self._normalize_task_category(task_type)
        if task_key in self.task_timeouts:
            return float(self.task_timeouts[task_key])
        return 300.0

    def _extract_error_message(self, result: Dict[str, Any]) -> str:
        if result.get("error"):
            return str(result.get("error"))
        if result.get("success") is False:
            return "Task finished with success=False"
        return "Unknown task error"

    def _result_has_error(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("error"):
            return True
        if result.get("success") is False:
            return True
        return False

    def _record_failure(
        self,
        *,
        task_id: str,
        agent_type: str,
        error_message: str,
        stack_trace: str,
        task_type: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        retry_count = 0
        if isinstance(metadata, dict):
            try:
                retry_count = int(metadata.get("retry_count", 0) or 0)
            except (TypeError, ValueError):
                retry_count = 0
        payload = {
            "prompt": prompt,
            "task_type": task_type,
            "metadata": metadata or {},
        }
        try:
            self.dead_letter_queue.add_failed_task(
                task_id=task_id,
                agent_type=agent_type or "unknown",
                error_message=error_message,
                stack_trace=stack_trace or "n/a",
                retry_count=retry_count,
                task_payload=payload,
            )
        except Exception as exc:
            self.logger.warning("Failed to persist DLQ record for task %s: %s", task_id, exc)

        if self.error_analytics is not None:
            try:
                self.error_analytics.record_error(
                    source=f"layer2.orchestrator.{agent_type or 'unknown'}",
                    message=error_message,
                    error_type="task_failure",
                    metadata={
                        "task_id": task_id,
                        "task_type": task_type,
                        "retry_count": retry_count,
                    },
                )
            except Exception as exc:
                self.logger.warning(
                    "Failed to persist error analytics for task %s: %s",
                    task_id,
                    exc,
                )

    def _build_simple_pseudocode(self, prompt: str) -> str:
        return (
            "PSEUDOCODE:\n"
            "1. Parse the user request.\n"
            "2. Define input and expected output.\n"
            "3. Implement core algorithm step by step.\n"
            "4. Add edge-case checks.\n"
            f"5. Validate result for request: {prompt[:200]}"
        )

    def _build_simple_summary(self, prompt: str) -> str:
        normalized = " ".join((prompt or "").split())
        if not normalized:
            return "Simple summary: no content provided."
        if len(normalized) <= 220:
            return f"Simple summary: {normalized}"
        return f"Simple summary: {normalized[:220]}..."

    async def _apply_graceful_degradation(
        self,
        *,
        task_id: str,
        prompt: str,
        task_type: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        category = self._normalize_task_category(task_type)
        if category == "researcher":
            search_result = await self.skill_system.use_skill("search_web", query=prompt)
            content = (
                "Researcher unavailable. Used web-search fallback.\n"
                f"{search_result}"
            )
            return {
                "content": content,
                "search_raw": search_result,
                "metadata": {
                    "agent": "fallback",
                    "fallback_strategy": "web_search",
                    "degraded": True,
                    "reason": reason,
                },
            }
        if category == "coder":
            return {
                "content": self._build_simple_pseudocode(prompt),
                "metadata": {
                    "agent": "fallback",
                    "fallback_strategy": "pseudocode",
                    "degraded": True,
                    "reason": reason,
                },
            }
        if category == "analyst":
            return {
                "content": self._build_simple_summary(prompt),
                "metadata": {
                    "agent": "fallback",
                    "fallback_strategy": "simple_summary",
                    "degraded": True,
                    "reason": reason,
                },
            }
        return None

    async def execute_task(
        self,
        task_id: str,
        prompt: str,
        task_type: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Выполняет задачу. Скелет — выбор агента и вызов process().
        Записывает шаги в EpisodicMemory при наличии.
        При наличии SemanticMemory: ищет похожие задачи и добавляет контекст.
        """
        self.logger.info(f"Task {task_id}: {task_type} — PENDING")
        if not self.agents:
            return {"error": f"No agent for task_type={task_type}"}

        agent = self._select_agent(task_type)
        if not agent:
            degraded = await self._apply_graceful_degradation(
                task_id=task_id,
                prompt=prompt,
                task_type=task_type,
                reason="No capable agent registered",
                metadata=metadata,
            )
            if degraded is not None:
                return degraded
            return {"error": f"No agent for task_type={task_type}"}

        if not await self.is_agent_healthy(agent):
            degraded = await self._apply_graceful_degradation(
                task_id=task_id,
                prompt=prompt,
                task_type=task_type,
                reason=f"Agent '{agent.name}' is unavailable",
                metadata=metadata,
            )
            if degraded is not None:
                return degraded
            return {"error": f"Agent '{agent.name}' is unavailable"}

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
        task = {
            "task_id": task_id,
            "prompt": enhanced_prompt,
            "task_type": task_type,
            "metadata": metadata or {},
        }

        try:
            timeout_seconds = self._resolve_timeout_seconds(task_type=task_type, agent=agent)
            result = await self._execute_with_distributed_lock(
                task_id=task_id,
                timeout_seconds=timeout_seconds,
                coroutine_factory=lambda: asyncio.wait_for(
                    agent.process(task),
                    timeout=timeout_seconds,
                ),
            )

            if self._result_has_error(result):
                error_message = self._extract_error_message(result)
                self.logger.warning("Task %s returned logical error: %s", task_id, error_message)
                self._record_failure(
                    task_id=task_id,
                    agent_type=agent.name,
                    error_message=error_message,
                    stack_trace="n/a",
                    task_type=task_type,
                    prompt=prompt,
                    metadata=metadata,
                )
                if self.memory:
                    self.memory.add_step(
                        task_id,
                        agent.name,
                        "process",
                        result,
                        metadata={"task_type": task_type, "failed": True},
                    )
                return result

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
        except asyncio.TimeoutError:
            error_message = (
                f"Task timed out after {self._resolve_timeout_seconds(task_type=task_type, agent=agent)}s"
            )
            self.logger.error("Task %s timeout for agent %s", task_id, agent.name)
            stack = traceback.format_exc()
            self._record_failure(
                task_id=task_id,
                agent_type=agent.name,
                error_message=error_message,
                stack_trace=stack,
                task_type=task_type,
                prompt=prompt,
                metadata=metadata,
            )
            if self.memory:
                self.memory.add_step(
                    task_id,
                    agent.name,
                    "process",
                    {"error": error_message},
                    metadata={"task_type": task_type, "failed": True, "timeout": True},
                )
            return {"error": error_message}
        except Exception as e:
            self.logger.error(f"Task {task_id} failed: {e}")
            stack = traceback.format_exc()
            self._record_failure(
                task_id=task_id,
                agent_type=agent.name,
                error_message=str(e),
                stack_trace=stack,
                task_type=task_type,
                prompt=prompt,
                metadata=metadata,
            )
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
                degraded = await self._apply_graceful_degradation(
                    task_id=step_task_id,
                    prompt=prompt,
                    task_type=step_type,
                    reason="No capable agent for step",
                    metadata={"step_index": i, "parent_task_id": task_id},
                )
                if degraded is not None:
                    steps_results.append(degraded)
                    if self.memory:
                        self.memory.add_step(
                            task_id,
                            "fallback",
                            "multi_step",
                            degraded,
                            metadata={"step_index": i, "step_type": step_type, "degraded": True},
                        )
                    context["previous_steps"].append(
                        {"content": degraded.get("content", ""), "result": degraded}
                    )
                    continue
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

            if not await self.is_agent_healthy(agent):
                degraded = await self._apply_graceful_degradation(
                    task_id=step_task_id,
                    prompt=prompt,
                    task_type=step_type,
                    reason=f"Agent '{agent.name}' is unavailable for step",
                    metadata={"step_index": i, "parent_task_id": task_id},
                )
                if degraded is not None:
                    steps_results.append(degraded)
                    if self.memory:
                        self.memory.add_step(
                            task_id,
                            "fallback",
                            "multi_step",
                            degraded,
                            metadata={"step_index": i, "step_type": step_type, "degraded": True},
                        )
                    context["previous_steps"].append(
                        {"content": degraded.get("content", ""), "result": degraded}
                    )
                    continue
                err = {
                    "error": f"Agent '{agent.name}' is unavailable",
                    "step_index": i,
                }
                steps_results.append(err)
                return {"error": err["error"], "steps_results": steps_results}

            task = {
                "task_id": step_task_id,
                "prompt": prompt,
                "task_type": step_type,
            }

            try:
                timeout_seconds = self._resolve_timeout_seconds(task_type=step_type, agent=agent)
                result = await self._execute_with_distributed_lock(
                    task_id=step_task_id,
                    timeout_seconds=timeout_seconds,
                    coroutine_factory=lambda: asyncio.wait_for(
                        agent.process(task, context=context),
                        timeout=timeout_seconds,
                    ),
                )
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
                self._record_failure(
                    task_id=step_task_id,
                    agent_type=agent.name,
                    error_message=str(e),
                    stack_trace=traceback.format_exc(),
                    task_type=step_type,
                    prompt=prompt,
                    metadata={"step_index": i, "parent_task_id": task_id},
                )
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
