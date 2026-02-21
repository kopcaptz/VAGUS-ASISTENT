"""
ReflectionAgent — агент рефлексии для улучшения промптов после оценки.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..types import AgentContext, AgentResult, AgentTask
from .base_agent import BaseAgent
from .protocols import LLMRouterProtocol


class ReflectionAgent(BaseAgent):
    """Генерирует refined prompt на основе результата и его оценки."""

    TASK_TYPES = ("reflection",)

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        description: str = "Агент рефлексии для улучшения промптов",
    ):
        super().__init__(name="reflection", llm_router=llm_router, description=description)

    def can_handle(self, task_type: str) -> bool:
        """Обрабатывает только reflection-задачи."""
        return (task_type or "").lower() in self.TASK_TYPES

    async def process(
        self,
        task: AgentTask,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        metadata = task.get("metadata", {})
        metadata_dict: Dict[str, Any] = metadata if isinstance(metadata, dict) else {}

        original_prompt = str(metadata_dict.get("original_prompt", "")).strip()
        agent_result = metadata_dict.get("agent_result")
        evaluation_result = metadata_dict.get("evaluation_result")
        agent_type = str(metadata_dict.get("agent_type", "")).strip() or "general"

        if not original_prompt:
            return {
                "content": "",
                "error": "Missing original_prompt for reflection",
                "metadata": {"agent": "reflection"},
            }
        if not isinstance(evaluation_result, dict):
            return {
                "content": "",
                "error": "Missing evaluation_result for reflection",
                "metadata": {"agent": "reflection"},
            }

        issues_raw = evaluation_result.get("issues", [])
        issues = [str(item) for item in issues_raw] if isinstance(issues_raw, list) else [str(issues_raw)]
        suggestions_raw = evaluation_result.get("suggestions", [])
        suggestions = (
            [str(item) for item in suggestions_raw]
            if isinstance(suggestions_raw, list)
            else [str(suggestions_raw)]
        )

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            original_prompt=original_prompt,
            agent_result=agent_result,
            issues=issues,
            suggestions=suggestions,
            agent_type=agent_type,
        )

        try:
            refined_prompt = await self._call_llm(f"{system_prompt}\n\n{user_prompt}")
        except Exception as exc:
            self.logger.exception("ReflectionAgent failed: %s", exc)
            return {
                "content": "",
                "error": f"Reflection failed: {exc}",
                "metadata": {"agent": "reflection", "agent_type": agent_type},
            }

        refined_prompt = refined_prompt.strip()
        if not refined_prompt:
            return {
                "content": "",
                "error": "Empty refined prompt from LLM",
                "metadata": {"agent": "reflection", "agent_type": agent_type},
            }

        # Guardrail: force-keep original goal in case LLM omits it.
        if original_prompt not in refined_prompt:
            refined_prompt = (
                f"Сохрани исходную цель задачи: {original_prompt}\n\n"
                f"Улучшенный промпт:\n{refined_prompt}"
            )

        return {
            "content": refined_prompt,
            "metadata": {
                "agent": "reflection",
                "agent_type": agent_type,
                "issues_count": len(issues),
                "issues": issues,
            },
        }

    def _build_system_prompt(self) -> str:
        return (
            "You are a reflection agent that rewrites prompts for a second attempt.\n"
            "Analyze issues from evaluation_result.issues and suggestions.\n"
            "Produce one refined prompt with concrete corrective instructions.\n"
            "Keep the original task goal unchanged.\n"
            "Adapt style to the target agent type (coder, researcher, analyst, etc.).\n"
            "Output plain text only (no markdown fences)."
        )

    def _build_user_prompt(
        self,
        *,
        original_prompt: str,
        agent_result: Any,
        issues: List[str],
        suggestions: List[str],
        agent_type: str,
    ) -> str:
        result_json = json.dumps(agent_result, ensure_ascii=False, default=str)
        issues_text = "\n".join(f"- {item}" for item in issues) if issues else "- no explicit issues"
        suggestions_text = (
            "\n".join(f"- {item}" for item in suggestions) if suggestions else "- no explicit suggestions"
        )
        return (
            f"Original prompt:\n{original_prompt}\n\n"
            f"Agent type:\n{agent_type}\n\n"
            f"Previous agent result:\n{result_json}\n\n"
            f"Issues from evaluation:\n{issues_text}\n\n"
            f"Suggestions from evaluation:\n{suggestions_text}\n\n"
            "Generate one refined prompt for re-run. Keep original objective and add explicit fixes."
        )

    async def _call_llm(self, prompt: str) -> str:
        content_parts: List[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts)


__all__ = ["ReflectionAgent"]
