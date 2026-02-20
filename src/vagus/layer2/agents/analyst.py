"""
AnalystAgent — агент для анализа данных, статистики и выводов.
Использует LLMRouter для аналитических запросов.
"""

from typing import Any, Optional

from ..types import AgentContext, AgentResult, AgentTask
from .base_agent import BaseAgent
from .protocols import LLMRouterProtocol


class AnalystAgent(BaseAgent):
    """
    Агент-аналитик: анализ данных, статистика, выводы, отчёты.
    """

    TASK_TYPES = ("analysis", "statistics", "insights", "report", "анализ", "отчёт")

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        description: str = "Агент для анализа данных, статистики и формирования выводов",
    ):
        super().__init__(name="analyst", llm_router=llm_router, description=description)

    def can_handle(self, task_type: str) -> bool:
        """Обрабатывает задачи типа analysis, statistics, insights, report."""
        task_lower = (task_type or "").lower()
        return any(t in task_lower for t in self.TASK_TYPES) or task_type == "default"

    async def process(
        self,
        task: AgentTask,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        """
        Анализирует данные/запрос через LLMRouter.
        Контекст предыдущих шагов передаётся в prompt при наличии.
        """
        prompt = task.get("prompt", "").strip()
        if not prompt:
            return {"content": "", "error": "Empty prompt", "metadata": {}}

        analysis_prompt = self._build_analysis_prompt(prompt, context or {})
        content = await self._call_llm(analysis_prompt)

        return {
            "content": content,
            "metadata": {"agent": "analyst", "task_type": task.get("task_type", "analysis")},
        }

    def _build_analysis_prompt(self, user_prompt: str, context: AgentContext) -> str:
        """Формирует промпт для аналитического запроса к LLM."""
        parts = ["Запрос на анализ:", user_prompt]
        if context:
            prev_results = context.get("previous_steps", [])
            if prev_results:
                parts.append("\nКонтекст предыдущих шагов:")
                for i, step in enumerate(prev_results, 1):
                    step_content = step.get("content", step.get("result", str(step)))
                    if isinstance(step_content, dict):
                        step_content = str(step_content)[:500]
                    parts.append(f"  Шаг {i}: {step_content}")
        parts.append("\nСформируй структурированный аналитический ответ: статистика, выводы, рекомендации.")
        return "\n".join(parts)

    async def _call_llm(self, prompt: str) -> str:
        """Вызывает LLMRouter и возвращает полный текст ответа."""
        content_parts: list[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts)


__all__ = ["AnalystAgent"]
