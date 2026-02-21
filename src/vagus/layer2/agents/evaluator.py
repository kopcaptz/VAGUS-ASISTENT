"""
EvaluatorAgent — агент для оценки качества результатов других агентов.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional, TypedDict, cast

from ..types import AgentContext, AgentTask
from .base_agent import BaseAgent
from .protocols import LLMRouterProtocol


class EvaluationResult(TypedDict):
    """Структурированный результат оценки."""

    score: float
    is_acceptable: bool
    issues: List[str]
    suggestions: List[str]


class EvaluatorAgent(BaseAgent):
    """Агент-оценщик качества ответов и артефактов других агентов."""

    TASK_TYPES = ("evaluation",)

    DEFAULT_CRITERIA = [
        "completeness",
        "accuracy",
        "relevance",
        "no hallucinations",
        "structure & clarity",
    ]

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        acceptable_threshold: float = 0.7,
        default_criteria: Optional[List[str]] = None,
        description: str = "Агент для оценки качества результатов других агентов",
    ):
        super().__init__(name="evaluator", llm_router=llm_router, description=description)
        self.acceptable_threshold = float(acceptable_threshold)
        self.default_criteria = list(default_criteria or self.DEFAULT_CRITERIA)

    def can_handle(self, task_type: str) -> bool:
        """Обрабатывает только задачи типа evaluation."""
        return (task_type or "").lower() in self.TASK_TYPES

    async def process(
        self,
        task: AgentTask,
        context: Optional[AgentContext] = None,
    ) -> EvaluationResult | dict[str, Any]:
        """
        Оценивает результат по критериям и возвращает структурированный verdict.
        """
        metadata = task.get("metadata", {})
        metadata_dict = metadata if isinstance(metadata, dict) else {}

        original_prompt = str(metadata_dict.get("original_prompt", "")).strip()
        if not original_prompt:
            original_prompt = str(task.get("prompt", "")).strip()

        agent_result = metadata_dict.get("agent_result")
        criteria_raw = metadata_dict.get("criteria")
        if isinstance(criteria_raw, list) and criteria_raw:
            criteria = [str(item) for item in criteria_raw if str(item).strip()]
        else:
            criteria = list(self.default_criteria)

        threshold = self.acceptable_threshold
        threshold_raw = metadata_dict.get("acceptable_threshold")
        if threshold_raw is not None:
            try:
                threshold = float(threshold_raw)
            except (TypeError, ValueError):
                pass
        threshold = max(0.0, min(1.0, threshold))

        if not original_prompt:
            return self._error_result(
                message="Missing original_prompt for evaluation",
                threshold=threshold,
            )

        if agent_result is None:
            return self._error_result(
                message="Missing agent_result for evaluation",
                threshold=threshold,
            )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            original_prompt=original_prompt,
            agent_result=agent_result,
            criteria=criteria,
            threshold=threshold,
        )

        try:
            llm_response = await self._call_llm(f"{system_prompt}\n\n{user_prompt}")
            parsed = self._parse_llm_json(llm_response)
            normalized = self._normalize_result(parsed, threshold)
            return cast(EvaluationResult, normalized)
        except Exception as exc:
            self.logger.exception("EvaluatorAgent failed: %s", exc)
            return self._error_result(
                message=f"Evaluation failed: {exc}",
                threshold=threshold,
            )

    def _build_system_prompt(self) -> str:
        return (
            "You are an evaluation agent. Assess another agent output and return STRICT JSON only.\n"
            "Evaluate against these dimensions: completeness, accuracy, relevance, no hallucinations, "
            "structure & clarity.\n"
            "Output schema:\n"
            "{\n"
            '  "score": float(0..1),\n'
            '  "issues": [string],\n'
            '  "suggestions": [string]\n'
            "}\n"
            "No markdown, no explanations outside JSON."
        )

    def _build_user_prompt(
        self,
        *,
        original_prompt: str,
        agent_result: Any,
        criteria: List[str],
        threshold: float,
    ) -> str:
        result_json = json.dumps(agent_result, ensure_ascii=False, default=str)
        criteria_text = ", ".join(criteria) if criteria else ", ".join(self.default_criteria)
        return (
            f"Original prompt:\n{original_prompt}\n\n"
            f"Agent result:\n{result_json}\n\n"
            f"Evaluation criteria: {criteria_text}\n"
            f"Acceptable threshold: {threshold}\n\n"
            "Return valid JSON."
        )

    async def _call_llm(self, prompt: str) -> str:
        content_parts: list[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts).strip()

    def _parse_llm_json(self, llm_text: str) -> dict[str, Any]:
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

    def _normalize_result(self, parsed: dict[str, Any], threshold: float) -> EvaluationResult:
        try:
            score = float(parsed.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))

        issues_raw = parsed.get("issues", [])
        suggestions_raw = parsed.get("suggestions", [])
        issues = [str(item) for item in issues_raw] if isinstance(issues_raw, list) else [str(issues_raw)]
        suggestions = (
            [str(item) for item in suggestions_raw]
            if isinstance(suggestions_raw, list)
            else [str(suggestions_raw)]
        )

        return EvaluationResult(
            score=score,
            is_acceptable=score >= threshold,
            issues=issues,
            suggestions=suggestions,
        )

    def _error_result(self, *, message: str, threshold: float) -> EvaluationResult:
        return EvaluationResult(
            score=0.0,
            is_acceptable=False,
            issues=[message],
            suggestions=["Retry evaluation with complete metadata and valid model response."],
        )


__all__ = ["EvaluatorAgent", "EvaluationResult"]
