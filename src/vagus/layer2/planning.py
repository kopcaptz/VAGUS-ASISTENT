"""
TaskPlanner — планировщик пошаговых задач на основе IntentResult.
Генерирует детальный план с зависимостями для MasterOrchestrator.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict

from .agents.protocols import LLMRouterProtocol
from .intent_classifier import IntentResult
from ..layer0.logging import get_logger

if TYPE_CHECKING:
    from .memory.procedural import ProceduralMemory

VALID_AGENT_TYPES = ("researcher", "coder", "analyst", "designer")
VALID_EXECUTION_MODES = ("sequential", "parallel", "mixed")
PRIMARY_INTENT_TO_AGENT: Dict[str, str] = {
    "research": "researcher",
    "code": "coder",
    "analysis": "analyst",
    "design": "designer",
    "mixed": "researcher",
}


class TaskStep(TypedDict):
    """Один шаг плана выполнения задачи."""

    step_id: str
    agent_type: str
    prompt: str
    depends_on: List[str]
    artefact_key: str


class TaskPlan(TypedDict):
    """План выполнения задачи с пошаговой декомпозицией."""

    plan_id: str
    steps: List[TaskStep]
    execution_mode: str


DEFAULT_PLAN_EXAMPLE = {
    "plan_id": "plan_abc123",
    "steps": [
        {
            "step_id": "s1",
            "agent_type": "coder",
            "prompt": "Сгенерируй код для задачи пользователя",
            "depends_on": [],
            "artefact_key": "generated_code",
        },
        {
            "step_id": "s2",
            "agent_type": "coder",
            "prompt": "Напиши тесты для сгенерированного кода",
            "depends_on": ["s1"],
            "artefact_key": "tests",
        },
    ],
    "execution_mode": "sequential",
}


class TaskPlanner:
    """Планировщик задач на основе IntentResult с LLM-генерацией плана."""

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        *,
        plan_examples: Optional[List[Dict[str, Any]]] = None,
        max_steps: int = 10,
        procedural_memory: Optional["ProceduralMemory"] = None,
        similarity_threshold: float = 0.7,
    ) -> None:
        self.llm_router = llm_router
        self.plan_examples = plan_examples if plan_examples is not None else [DEFAULT_PLAN_EXAMPLE]
        self.max_steps = max(1, min(50, max_steps))
        self.procedural_memory = procedural_memory
        self._similarity_threshold = max(0.0, min(1.0, similarity_threshold))
        self.logger = get_logger("layer2.task_planner")

    async def create_plan(self, intent: IntentResult) -> TaskPlan:
        """Создаёт план выполнения на основе результата классификации намерений."""
        if self.procedural_memory and self.procedural_memory.enabled:
            similar = await self.procedural_memory.find_similar_plan(
                intent, threshold=self._similarity_threshold
            )
            if similar:
                await self.procedural_memory.increment_usage_count(similar.get("plan_id", ""))
                plan_id = similar.get("plan_id", "")
                new_plan_id = f"plan_{uuid.uuid4().hex[:12]}"
                result = dict(similar)
                result["plan_id"] = new_plan_id
                steps = result.get("steps", [])
                result["steps"] = [
                    {**s, "step_id": s.get("step_id", f"s{i}")}
                    for i, s in enumerate(steps)
                ]
                self.logger.info("Reused plan from ProceduralMemory (original %s)", plan_id)
                return result

        prompt = self._build_prompt(intent)
        try:
            llm_response = await self._call_llm(prompt)
            parsed = self._parse_llm_json(llm_response)
            return self._normalize_plan(parsed)
        except Exception as exc:
            self.logger.warning("Task planning failed, using fallback plan: %s", exc)
            return self._fallback_plan(intent)

    def _build_prompt(self, intent: IntentResult) -> str:
        primary = intent.get("primary_intent", "mixed")
        sub_intents = intent.get("sub_intents") or []
        entities = intent.get("entities") or {}
        complexity = intent.get("complexity", "moderate")
        entities_json = json.dumps(entities, ensure_ascii=False)
        sub_json = json.dumps(sub_intents, ensure_ascii=False)

        schema = (
            "{\n"
            '  "plan_id": "string (unique)",\n'
            '  "steps": [\n'
            "    {\n"
            '      "step_id": "string",\n'
            '      "agent_type": "researcher|coder|analyst|designer",\n'
            '      "prompt": "string (concrete prompt for agent)",\n'
            '      "depends_on": ["step_id"],\n'
            '      "artefact_key": "string"\n'
            "    }\n"
            "  ],\n"
            '  "execution_mode": "sequential|parallel|mixed"\n'
            "}"
        )
        examples_text = ""
        for ex in self.plan_examples:
            examples_text += "\n" + json.dumps(ex, ensure_ascii=False, indent=2)

        return (
            "You are a task planner. Decompose user intent into concrete execution steps. Return STRICT JSON only.\n"
            "Output schema:\n"
            f"{schema}\n\n"
            "Rules: step_id must be unique; depends_on must reference existing step_id; artefact_key unique per plan;\n"
            f"execution_mode: simple->sequential, moderate->sequential/mixed, complex->parallel/mixed.\n\n"
            "Examples:"
            f"{examples_text}\n\n"
            f"Intent to plan: primary_intent={primary}, sub_intents={sub_json}, entities={entities_json}, complexity={complexity}\n\n"
            "Return valid JSON only, no markdown."
        )

    async def _call_llm(self, prompt: str) -> str:
        content_parts: List[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts).strip()

    def _parse_llm_json(self, llm_text: str) -> Dict[str, Any]:
        if not llm_text:
            raise ValueError("Empty LLM response")
        candidate = llm_text.strip()
        if "```" in candidate:
            candidate = candidate.replace("```json", "").replace("```", "").strip()
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            candidate = candidate[start : end + 1]
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("LLM response JSON must be an object")
        return parsed

    def _normalize_plan(self, parsed: Dict[str, Any]) -> TaskPlan:
        plan_id = str(parsed.get("plan_id", "")).strip() or f"plan_{uuid.uuid4().hex[:12]}"
        execution_mode = str(parsed.get("execution_mode", "sequential")).strip().lower()
        if execution_mode not in VALID_EXECUTION_MODES:
            execution_mode = "sequential"

        steps_raw = parsed.get("steps", [])
        if not isinstance(steps_raw, list):
            steps_raw = []
        steps_raw = steps_raw[: self.max_steps]

        valid_step_ids: set[str] = set()
        for raw in steps_raw:
            if isinstance(raw, dict):
                sid = str(raw.get("step_id", "")).strip() or uuid.uuid4().hex[:8]
                valid_step_ids.add(sid)
        seen_step_ids: set[str] = set()
        artefact_counts: Dict[str, int] = {}
        normalized_steps: List[TaskStep] = []

        for i, raw in enumerate(steps_raw):
            if not isinstance(raw, dict):
                continue
            step_id = str(raw.get("step_id", "")).strip() or uuid.uuid4().hex[:8]
            if step_id in seen_step_ids:
                step_id = f"{step_id}_{i}"
            seen_step_ids.add(step_id)
            valid_step_ids.add(step_id)

            agent_type = str(raw.get("agent_type", "coder")).strip().lower()
            if agent_type not in VALID_AGENT_TYPES:
                agent_type = "coder"

            prompt_text = str(raw.get("prompt", "")).strip() or "Выполни задачу."
            depends_on_raw = raw.get("depends_on", [])
            depends_on = [
                str(d).strip()
                for d in (depends_on_raw if isinstance(depends_on_raw, list) else [])
                if str(d).strip() and str(d).strip() in valid_step_ids
            ]

            artefact_key = str(raw.get("artefact_key", "")).strip() or f"artefact_{i}"
            base_key = artefact_key
            count = artefact_counts.get(base_key, 0)
            count += 1
            artefact_counts[base_key] = count
            if count > 1:
                artefact_key = f"{base_key}_{count}"

            normalized_steps.append(
                TaskStep(
                    step_id=step_id,
                    agent_type=agent_type,
                    prompt=prompt_text,
                    depends_on=depends_on,
                    artefact_key=artefact_key,
                )
            )

        if not normalized_steps:
            agent = PRIMARY_INTENT_TO_AGENT.get("mixed", "coder")
            step_id = uuid.uuid4().hex[:8]
            normalized_steps = [
                TaskStep(
                    step_id=step_id,
                    agent_type=agent,
                    prompt="Выполни задачу по намерению пользователя.",
                    depends_on=[],
                    artefact_key="result",
                )
            ]

        return TaskPlan(
            plan_id=plan_id,
            steps=normalized_steps,
            execution_mode=execution_mode,
        )

    def _fallback_plan(self, intent: IntentResult) -> TaskPlan:
        primary = intent.get("primary_intent", "mixed")
        agent = PRIMARY_INTENT_TO_AGENT.get(primary, "coder")
        step_id = uuid.uuid4().hex[:8]
        return TaskPlan(
            plan_id=f"plan_fallback_{uuid.uuid4().hex[:8]}",
            steps=[
                TaskStep(
                    step_id=step_id,
                    agent_type=agent,
                    prompt="Выполни задачу по намерению пользователя.",
                    depends_on=[],
                    artefact_key="result",
                )
            ],
            execution_mode="sequential",
        )


def task_plan_get_ordered_steps(plan: TaskPlan) -> List[TaskStep]:
    """
    Возвращает шаги плана в топологическом порядке (depends_on first).
    """
    steps = plan.get("steps", [])
    if not steps:
        return []
    step_by_id = {s["step_id"]: s for s in steps}
    ordered: List[TaskStep] = []
    visited: set[str] = set()

    def visit(sid: str) -> None:
        if sid in visited:
            return
        visited.add(sid)
        step = step_by_id.get(sid)
        if step:
            for dep in step.get("depends_on", []):
                visit(dep)
            ordered.append(step)

    for s in steps:
        visit(s["step_id"])

    return ordered


def task_plan_to_multi_steps(plan: TaskPlan) -> List[Dict[str, Any]]:
    """
    Преобразует TaskPlan в List[MultiStepTask] для execute_multi_step_task.
    Шаги упорядочены топологически по depends_on.
    """
    ordered = task_plan_get_ordered_steps(plan)
    return [{"type": s["agent_type"], "prompt": s["prompt"]} for s in ordered]


def create_task_planner(
    llm_router: LLMRouterProtocol,
    config: Optional[Dict[str, Any]] = None,
    *,
    procedural_memory: Optional["ProceduralMemory"] = None,
    similarity_threshold: float = 0.7,
) -> TaskPlanner:
    """Создаёт TaskPlanner из конфигурации layer2.task_planner."""
    cfg = config or {}
    max_steps = int(cfg.get("max_steps", 10))
    plan_examples = cfg.get("plan_examples")
    return TaskPlanner(
        llm_router,
        max_steps=max_steps,
        plan_examples=plan_examples,
        procedural_memory=procedural_memory,
        similarity_threshold=similarity_threshold,
    )


__all__ = [
    "TaskPlanner",
    "TaskPlan",
    "TaskStep",
    "create_task_planner",
    "task_plan_get_ordered_steps",
    "task_plan_to_multi_steps",
]
