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

from .agent_registry import AgentRegistry
from .communication import CommunicationLayer, SharedBlackboard
from .agents.base_agent import BaseAgent
from .dead_letter_queue import DeadLetterQueueStorage
from .intent_classifier import IntentClassifier, IntentResult
from .planning import TaskPlan, TaskPlanner, TaskStep, task_plan_get_ordered_steps
from .skills import SkillSystem
from .types import AgentContext, AgentMetadata, AgentResult, AgentTask, MultiStepTask
from ..layer0.logging import get_logger

if TYPE_CHECKING:
    from .memory.coherence import CoherenceMonitor
    from .memory.consolidation_handler import MemoryConsolidationHandler
    from .memory.synaptic_handler import SynapticTrainingHandler
    from .memory.episodic import EpisodicMemory
    from .memory.manager import MemoryManager
    from .memory.procedural import ProceduralMemory
    from .memory.summarizer import ConversationSummarizer
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
        enable_reflexion: bool = True,
        max_reflection_iterations: int = 2,
        reflection_threshold: float = 0.7,
    ):
        """
        Args:
            communication: Слой коммуникации
            agents: Список агентов (Researcher, Coder, ...)
            memory: EpisodicMemory для записи истории выполнения (опционально)
            semantic_memory: SemanticMemory для векторного поиска похожих задач (опционально)
            enable_reflexion: Включить Reflexion Loop (оценка + рефлексия при низком score)
            max_reflection_iterations: Максимум попыток рефлексии
            reflection_threshold: Порог score для признания результата приемлемым (0..1)
        """
        self.communication = communication
        self.enable_reflexion = enable_reflexion
        self.max_reflection_iterations = max(max_reflection_iterations, 1)
        self.reflection_threshold = max(0.0, min(1.0, reflection_threshold))
        self.agents = agents or []
        self.agent_registry = AgentRegistry(self.agents)
        self.agents = self.agent_registry.list()
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
            "evaluator": 120.0,
            "designer": 240.0,
        }
        if not isinstance(task_timeouts, dict):
            return defaults
        normalized = dict(defaults)
        for key in ("researcher", "coder", "analyst", "evaluator", "designer"):
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
        self.agent_registry.register(agent)
        self.agents = self.agent_registry.list()
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
        if any(x in task_lower for x in ("evaluation", "evaluate", "assessment", "review", "оценка")):
            return "evaluator"
        if any(
            x in task_lower
            for x in ("design", "ui", "ux", "layout", "mockup", "интерфейс", "дизайн")
        ):
            return "designer"
        return "default"

    def _resolve_timeout_seconds(self, *, task_type: str, agent: BaseAgent) -> float:
        agent_key = (getattr(agent, "name", "") or "").lower()
        if agent_key in self.task_timeouts:
            return float(self.task_timeouts[agent_key])
        task_key = self._normalize_task_category(task_type)
        if task_key in self.task_timeouts:
            return float(self.task_timeouts[task_key])
        return 300.0

    def _extract_error_message(self, result: AgentResult) -> str:
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
        metadata: Optional[AgentMetadata | dict[str, Any]] = None,
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

    def _build_simple_layout_plan(self, prompt: str) -> str:
        normalized = " ".join((prompt or "").split())
        return (
            "UI LAYOUT PLAN:\n"
            "1. Define page structure (header/content/footer).\n"
            "2. Use responsive grid with mobile-first breakpoints.\n"
            "3. Ensure contrast and focus states for accessibility.\n"
            f"4. Prioritize core user flow for: {normalized[:160]}"
        )

    def _build_simple_evaluation(self, prompt: str) -> dict[str, Any]:
        normalized = " ".join((prompt or "").split())
        return {
            "score": 0.3,
            "is_acceptable": False,
            "issues": [f"Evaluator unavailable for prompt: {normalized[:180]}"],
            "suggestions": ["Retry evaluation after evaluator agent recovers."],
        }

    async def _run_reflexion_loop(
        self,
        *,
        task_id: str,
        prompt: str,
        task_type: str,
        metadata: Optional[AgentMetadata | dict[str, Any]],
        agent: BaseAgent,
        task: AgentTask,
        result: AgentResult,
        timeout_seconds: float,
    ) -> tuple[AgentResult, List[Dict[str, Any]]]:
        """Reflexion loop: evaluate -> reflect -> retry up to max_reflection_iterations."""
        meta = metadata or {}
        meta_dict = meta if isinstance(meta, dict) else {}
        enable = self.enable_reflexion and meta_dict.get("enable_reflexion", True) is not False
        if not enable:
            return (result, [])
        task_lower = (task_type or "").lower()
        if task_lower in ("evaluation", "reflection"):
            return (result, [])

        max_iter = meta_dict.get("max_reflection_iterations")
        if max_iter is not None:
            try:
                max_iter = max(1, int(max_iter))
            except (TypeError, ValueError):
                max_iter = self.max_reflection_iterations
        else:
            max_iter = self.max_reflection_iterations

        threshold = meta_dict.get("reflection_threshold")
        if threshold is not None:
            try:
                threshold = max(0.0, min(1.0, float(threshold)))
            except (TypeError, ValueError):
                threshold = self.reflection_threshold
        else:
            threshold = self.reflection_threshold

        evaluator = self.agent_registry.find_by_task_type("evaluation")
        reflection_agent = self.agent_registry.find_by_task_type("reflection")
        if not evaluator or not reflection_agent:
            return (result, [])

        self.logger.info(
            "Task %s: starting reflexion loop, threshold=%.2f, max_iterations=%d",
            task_id, threshold, max_iter,
        )
        evaluated: List[tuple[AgentResult, float]] = []
        current_result = result
        task_copy = dict(task)

        for i in range(max_iter):
            eval_task: AgentTask = {
                "task_id": f"{task_id}_eval_{i}",
                "prompt": "",
                "task_type": "evaluation",
                "metadata": {
                    "original_prompt": prompt,
                    "agent_result": current_result,
                },
            }
            try:
                eval_result = await evaluator.process(eval_task)
            except Exception as exc:
                self.logger.warning("Task %s: evaluator failed: %s", task_id, exc)
                break
            if self._result_has_error(eval_result):
                break
            score = float(eval_result.get("score", 0.0))
            evaluated.append((current_result, score))
            self.logger.info(
                "Task %s: evaluation score=%.2f, acceptable=%s",
                task_id, score, score >= threshold,
            )
            if score >= threshold:
                self.logger.info("Task %s: reflexion completed, score=%.2f, attempts=%d", task_id, score, i + 1)
                return (current_result, [{"score": s, "iteration": j} for j, (_, s) in enumerate(evaluated)])

            if i == max_iter - 1:
                break
            ref_task: AgentTask = {
                "task_id": f"{task_id}_ref_{i}",
                "prompt": "",
                "task_type": "reflection",
                "metadata": {
                    "original_prompt": prompt,
                    "agent_result": current_result,
                    "evaluation_result": eval_result,
                    "agent_type": agent.name,
                },
            }
            try:
                ref_result = await reflection_agent.process(ref_task)
            except Exception as exc:
                self.logger.warning("Task %s: reflection failed: %s", task_id, exc)
                break
            if self._result_has_error(ref_result):
                break
            refined_prompt = (ref_result.get("content") or "").strip()
            if not refined_prompt:
                break
            self.logger.info(
                "Task %s: refinement iteration %d, refined_prompt_len=%d",
                task_id, i, len(refined_prompt),
            )
            task_copy["prompt"] = refined_prompt
            task_copy["metadata"] = {**(meta_dict or {}), "reflexion_iteration": i}
            try:
                current_result = await asyncio.wait_for(
                    agent.process(task_copy),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError:
                break
            if self._result_has_error(current_result):
                break

        best = max(evaluated, key=lambda x: x[1]) if evaluated else (result, 0.0)
        attempts = [{"score": s, "iteration": j} for j, (_, s) in enumerate(evaluated)]
        self.logger.info(
            "Task %s: reflexion completed, best_score=%.2f, attempts=%d",
            task_id, best[1], len(attempts),
        )
        return (best[0], attempts)

    async def _apply_graceful_degradation(
        self,
        *,
        task_id: str,
        prompt: str,
        task_type: str,
        reason: str,
        metadata: Optional[AgentMetadata | dict[str, Any]] = None,
    ) -> Optional[AgentResult]:
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
        if category == "designer":
            return {
                "content": self._build_simple_layout_plan(prompt),
                "metadata": {
                    "agent": "fallback",
                    "fallback_strategy": "layout_plan",
                    "degraded": True,
                    "reason": reason,
                },
            }
        if category == "evaluator":
            return {
                **self._build_simple_evaluation(prompt),
                "metadata": {
                    "agent": "fallback",
                    "fallback_strategy": "rule_based_evaluation",
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
        metadata: Optional[AgentMetadata | dict[str, Any]] = None,
    ) -> AgentResult:
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
        task: AgentTask = {
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

            result, reflexion_attempts = await self._run_reflexion_loop(
                task_id=task_id,
                prompt=prompt,
                task_type=task_type,
                metadata=metadata,
                agent=agent,
                task=task,
                result=result,
                timeout_seconds=timeout_seconds,
            )
            if reflexion_attempts:
                meta = result.get("metadata") or {}
                if not isinstance(meta, dict):
                    meta = dict(meta)
                meta["reflexion_attempts"] = reflexion_attempts
                result = dict(result)
                result["metadata"] = meta

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
        steps: List[MultiStepTask],
    ) -> AgentResult:
        """
        Выполняет многошаговую задачу (цепочку шагов).
        Каждый шаг: {"type": "research"|"code"|"analysis", "prompt": "..."}
        Результаты предыдущих шагов передаются в контекст следующим.
        Записывает каждый шаг в EpisodicMemory.
        """
        if not steps:
            return {"error": "Empty steps", "steps_results": []}

        self.logger.info(f"Multi-step task {task_id}: {len(steps)} steps")
        steps_results: list[AgentResult] = []
        context: AgentContext = {"previous_steps": []}

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

            task: AgentTask = {
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
    ) -> AgentResult:
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

        async def _run_one(tid: str, prompt: str, ttype: str) -> AgentResult:
            async with semaphore:
                return await self.execute_task(tid, prompt, ttype)

        self.logger.info(f"Parallel execution: {len(task_ids)} tasks, max_concurrency={max_concurrency}")
        coros = [_run_one(tid, p, t) for tid, p, t in zip(task_ids, prompts, task_types)]
        raw_results = await asyncio.gather(*coros, return_exceptions=True)

        results: dict[str, AgentResult] = {}
        errors: dict[str, str] = {}
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
        return self.agent_registry.find_by_task_type(task_type)


class MasterOrchestrator:
    """
    Главный оркестратор: Intent -> Plan -> Execution -> Synthesis.
    Объединяет IntentClassifier, TaskPlanner, SharedBlackboard в единый процесс.
    """

    def __init__(
        self,
        llm_router: Any,
        intent_classifier: IntentClassifier,
        task_planner: TaskPlanner,
        shared_blackboard: SharedBlackboard,
        agent_registry: AgentRegistry,
        *,
        event_bus: Optional[CommunicationLayer] = None,
        procedural_memory: Optional["ProceduralMemory"] = None,
        conversation_summarizer: Optional["ConversationSummarizer"] = None,
        memory_manager: Optional["MemoryManager"] = None,
        coherence_monitor: Optional["CoherenceMonitor"] = None,
        memory_consolidation_handler: Optional["MemoryConsolidationHandler"] = None,
        synaptic_handler: Optional["SynapticTrainingHandler"] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.llm_router = llm_router
        self.intent_classifier = intent_classifier
        self.task_planner = task_planner
        self.shared_blackboard = shared_blackboard
        self.agent_registry = agent_registry
        self.event_bus = event_bus
        self.procedural_memory = procedural_memory
        self.conversation_summarizer = conversation_summarizer
        self.memory_manager = memory_manager
        self.coherence_monitor = coherence_monitor
        self.memory_consolidation_handler = memory_consolidation_handler
        self.synaptic_handler = synaptic_handler
        self.config = config or {}
        self.logger = get_logger("layer2.master_orchestrator")

    def _event_payload(self, payload: Dict[str, Any], api_task_id: Optional[str] = None) -> Dict[str, Any]:
        """Добавляет trace_id и опционально api_task_id в payload для Event Bus."""
        result = dict(payload)
        if api_task_id:
            result["api_task_id"] = api_task_id
        try:
            from ..logging import get_trace_id
            tid = get_trace_id()
            if tid:
                result["trace_id"] = tid
        except Exception:
            pass
        return result

    def _result_has_error(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("error"):
            return True
        if result.get("success") is False:
            return True
        return False

    async def _perform_memory_lookup(
        self, task: dict, tenant_id: str
    ) -> dict:
        """Единый lookup: SemanticMemory + ProceduralMemory через MemoryManager."""
        if not self.memory_manager:
            return {"history": [], "relevant_knowledge": [], "similar_plans": []}
        return await self.memory_manager.get_context_for_task(task, tenant_id)

    async def execute_task(
        self, task_id: str, prompt: str, task_type: Optional[str] = None
    ) -> AgentResult:
        """
        API-совместимый интерфейс: делегирует в process_request.
        task_type игнорируется — MasterOrchestrator сам определяет intent.
        api_task_id передаётся в событийный поток для связи с WebSocket /ws/tasks/{id}.
        """
        result = await self.process_request(prompt, api_task_id=task_id)
        if isinstance(result, dict) and "metadata" in result:
            meta = result.get("metadata") or {}
            result = {**result, "metadata": {**meta, "task_id": task_id}}
        return result

    async def process_request(self, user_input: str, api_task_id: Optional[str] = None) -> AgentResult:
        """
        Обрабатывает запрос пользователя: classify -> plan -> execute -> synthesize.
        """
        self.logger.info("process_request: user_input=%s", (user_input or "")[:100])

        intent_result: IntentResult
        try:
            intent_result = await self.intent_classifier.classify(user_input or "")
        except Exception as exc:
            self.logger.warning("Intent classification failed, using fallback: %s", exc)
            intent_result = {
                "primary_intent": "mixed",
                "sub_intents": [],
                "entities": {},
                "complexity": "moderate",
                "confidence": 0.5,
            }

        self.logger.info(
            "process_request: intent=%s complexity=%s confidence=%.2f",
            intent_result.get("primary_intent"),
            intent_result.get("complexity"),
            intent_result.get("confidence", 0),
        )

        tenant_id = self.config.get("tenant_id", "default")
        from .memory.procedural import intent_to_summary
        task_for_lookup = {
            "task_id": "pending",
            "description": user_input or "",
            "intent_summary": intent_to_summary(intent_result),
        }
        memory_context = await self._perform_memory_lookup(task_for_lookup, tenant_id)
        self.logger.debug(
            "memory_lookup: history=%d knowledge=%d similar_plans=%d",
            len(memory_context.get("history", [])),
            len(memory_context.get("relevant_knowledge", [])),
            len(memory_context.get("similar_plans", [])),
        )

        plan: TaskPlan
        try:
            plan = await self.task_planner.create_plan(intent_result)
        except Exception as exc:
            self.logger.warning("Task planning failed, using fallback: %s", exc)
            plan = {
                "plan_id": f"plan_fallback_{uuid.uuid4().hex[:8]}",
                "steps": [
                    {
                        "step_id": uuid.uuid4().hex[:8],
                        "agent_type": "coder",
                        "prompt": str(user_input or "Выполни задачу."),
                        "depends_on": [],
                        "artefact_key": "result",
                    }
                ],
                "execution_mode": "sequential",
            }

        plan_id = plan.get("plan_id") or uuid.uuid4().hex
        steps = task_plan_get_ordered_steps(plan)
        self.logger.info(
            "process_request: plan_id=%s steps=%d execution_mode=%s",
            plan_id,
            len(steps),
            plan.get("execution_mode", "sequential"),
        )

        if self.event_bus:
            await self.event_bus.publish_event(
                "task.planned",
                self._event_payload({"plan_id": plan_id, "steps": [s.get("step_id") for s in steps], "execution_mode": plan.get("execution_mode")}, api_task_id=api_task_id),
                task_id=plan_id,
                tenant_id=tenant_id,
            )

        step_by_id = {s["step_id"]: s for s in plan.get("steps", [])}

        for step in steps:
            step_id = step["step_id"]
            agent_type = step.get("agent_type", "coder")
            artefact_key = step.get("artefact_key", "result")
            prompt = step.get("prompt", "").strip() or "Выполни задачу."

            self.logger.info(
                "process_request: step step_id=%s agent_type=%s artefact_key=%s",
                step_id,
                agent_type,
                artefact_key,
            )

            agent = self.agent_registry.find_by_name(agent_type)
            if not agent:
                self.logger.warning("No agent for agent_type=%s, skipping step", agent_type)
                task_id_skip = f"{plan_id}_{step_id}"
                if self.event_bus:
                    await self.event_bus.publish_event(
                        "task.failed",
                        self._event_payload({"step_id": step_id, "agent_type": agent_type, "error": f"No agent for {agent_type}"}, api_task_id=api_task_id),
                        task_id=task_id_skip,
                        tenant_id=tenant_id,
                    )
                await self.shared_blackboard.write(
                    plan_id,
                    artefact_key,
                    {"error": f"No agent for {agent_type}"},
                )
                continue

            context_parts: List[str] = []
            for dep_id in step.get("depends_on", []):
                dep_step = step_by_id.get(dep_id)
                if dep_step:
                    dep_key = dep_step.get("artefact_key")
                    if dep_key:
                        dep_artefact = await self.shared_blackboard.read(plan_id, dep_key)
                        if dep_artefact is not None:
                            content = dep_artefact.get("content", dep_artefact) if isinstance(dep_artefact, dict) else dep_artefact
                            context_parts.append(f"[{dep_key}]: {str(content)[:500]}")

            enriched_prompt = prompt
            if context_parts:
                enriched_prompt = "Context from previous steps:\n" + "\n".join(context_parts) + "\n\nTask: " + prompt

            task: AgentTask = {
                "task_id": f"{plan_id}_{step_id}",
                "prompt": enriched_prompt,
                "task_type": agent_type,
                "metadata": {"plan_id": plan_id, "step_id": step_id, "original_prompt": user_input},
            }
            task_id = f"{plan_id}_{step_id}"

            if self.event_bus:
                await self.event_bus.publish_event(
                    "agent.started",
                    self._event_payload({"step_id": step_id, "agent_type": agent_type, "artefact_key": artefact_key}, api_task_id=api_task_id),
                    task_id=task_id,
                    tenant_id=tenant_id,
                )

            try:
                result = await agent.process(task)
            except Exception as exc:
                self.logger.exception("Step %s failed: %s", step_id, exc)
                result = {"error": str(exc), "content": ""}
                if self.event_bus:
                    await self.event_bus.publish_event(
                        "task.failed",
                        self._event_payload({"step_id": step_id, "agent_type": agent_type, "error": str(exc)}, api_task_id=api_task_id),
                        task_id=task_id,
                        tenant_id=tenant_id,
                    )

            if self.event_bus:
                await self.event_bus.publish_event(
                    "agent.finished",
                    self._event_payload({"step_id": step_id, "agent_type": agent_type, "has_error": self._result_has_error(result)}, api_task_id=api_task_id),
                    task_id=task_id,
                    tenant_id=tenant_id,
                )

            await self.shared_blackboard.write(plan_id, artefact_key, result)

            current_artifact_id: Optional[str] = None
            dep_artifact_ids: List[str] = []
            if self.memory_manager and self.memory_manager.artifact_kb and not self._result_has_error(result):
                try:
                    content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                    if content:
                        current_artifact_id = await self.memory_manager.save_artifact(
                            content=content,
                            artifact_type=agent_type,
                            source_step=step_id,
                            tenant_id=tenant_id,
                            plan_id=plan_id,
                            key=artefact_key,
                        )
                    for dep_id in step.get("depends_on", []):
                        dep_step = step_by_id.get(dep_id)
                        if dep_step:
                            dep_key = dep_step.get("artefact_key")
                            if dep_key:
                                aid = await self.memory_manager.artifact_kb.get_artifact_id_by_plan_key(
                                    tenant_id, plan_id, dep_key
                                )
                                if aid:
                                    dep_artifact_ids.append(aid)
                except Exception as exc:
                    self.logger.debug("Failed to save artifact for quality_gate: %s", exc)

            if self.memory_manager:
                await self.memory_manager.save_episodic_step(
                    tenant_id=tenant_id,
                    task_id=plan_id,
                    agent_type=agent_type,
                    action="process",
                    result=result,
                    metadata={"step_id": step_id, "artefact_key": artefact_key},
                )
                if self.coherence_monitor:
                    history = await self.memory_manager.episodic.get_recent_history(
                        tenant_id, plan_id, limit=100
                    )
                    if await self.coherence_monitor.should_summarize(len(history)):
                        await self.coherence_monitor.summarize_and_replace(
                            plan_id, self.memory_manager.episodic, tenant_id
                        )

            if self._result_has_error(result):
                self.logger.warning("Step %s returned error: %s", step_id, result.get("error"))
                if self.event_bus:
                    await self.event_bus.publish_event(
                        "task.failed",
                        self._event_payload({"step_id": step_id, "agent_type": agent_type, "error": result.get("error", "Unknown")}, api_task_id=api_task_id),
                        task_id=task_id,
                        tenant_id=tenant_id,
                    )
            elif self.event_bus:
                qg_payload = {
                    "step_id": step_id,
                    "agent_type": agent_type,
                    "artefact_key": artefact_key,
                    "artifact_id": current_artifact_id,
                    "dep_artifact_ids": dep_artifact_ids,
                }
                await self.event_bus.publish_event(
                    "quality_gate.passed",
                    self._event_payload(qg_payload, api_task_id=api_task_id),
                    task_id=task_id,
                    tenant_id=tenant_id,
                )

        artefacts = await self.shared_blackboard.read_all(plan_id)
        content_parts = []
        for key, val in artefacts.items():
            if val is not None:
                cnt = val.get("content", val) if isinstance(val, dict) else val
                if cnt and not (isinstance(val, dict) and val.get("error")):
                    content_parts.append(str(cnt))
        final_content = "\n\n---\n\n".join(content_parts) if content_parts else ""

        self.logger.info("process_request: plan_id=%s artefacts_count=%d", plan_id, len(artefacts))

        has_error = any(
            isinstance(v, dict) and v.get("error")
            for v in artefacts.values()
            if v is not None
        )
        success = not has_error and bool(final_content and final_content != "No results produced.")
        task_completed_payload = self._event_payload({
            "plan_id": plan_id,
            "artefacts": list(artefacts.keys()),
            "content_length": len(final_content),
            "task_id": plan_id,
            "prompt": user_input or "",
            "intent_summary": intent_to_summary(intent_result),
            "plan_json": json.dumps(plan, ensure_ascii=False, default=str),
            "success": success,
        }, api_task_id=api_task_id)
        if self.event_bus:
            await self.event_bus.publish_event(
                "task.completed",
                task_completed_payload,
                task_id=plan_id,
                tenant_id=tenant_id,
            )

        # Прямой вызов consolidation только при Pub/Sub или in-memory; при Streams — через Event Bus
        if self.memory_consolidation_handler and not getattr(self.event_bus, "uses_streams", False):
            await self.memory_consolidation_handler.handle_task_completed(
                {
                    "task_id": plan_id,
                    "prompt": user_input or "",
                    "intent_summary": intent_to_summary(intent_result),
                    "plan_json": json.dumps(plan, ensure_ascii=False, default=str),
                    "success": success,
                },
                tenant_id,
            )

        return {
            "content": final_content or "No results produced.",
            "metadata": {"plan_id": plan_id, "artefacts": list(artefacts.keys())},
        }
