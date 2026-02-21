"""
ConversationSummarizer — сжатие длинных диалогов для экономии контекста.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..agents.protocols import LLMRouterProtocol
from ...layer0.logging import get_logger

RESULT_SNIPPET_MAX_LEN = 200

SYSTEM_PROMPT = """You are a dialogue summarizer. Given a conversation history (agent steps), produce a concise summary.

Include: goal, main decisions, critical issues and resolutions, final outcome.
Exclude: technical minutiae, repeated information, raw code blocks.

Output 50-500 words. Language: same as input (Russian/English).
"""

EXAMPLE_INPUT = """Step 1 [researcher] search_web:
  Result: Found documentation on FastAPI. Key points: async support, OpenAPI schema.

Step 2 [coder] process:
  Result: Generated Python script using FastAPI routes."""

EXAMPLE_OUTPUT = """Goal: Create FastAPI application. Researcher found documentation. Coder generated routes. Result: working script."""

FEW_SHOT = f"""

Example input:
{EXAMPLE_INPUT}

Example output:
{EXAMPLE_OUTPUT}

"""


class ConversationSummarizer:
    """
    Сжимает историю диалога (шаги EpisodicMemory) в краткое резюме через LLM.
    """

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        *,
        enabled: bool = True,
        max_input_steps: int = 50,
        min_summary_words: int = 50,
        max_summary_words: int = 500,
    ) -> None:
        self.llm_router = llm_router
        self.enabled = enabled
        self.max_input_steps = max(max_input_steps, 1)
        self.min_summary_words = max(min_summary_words, 10)
        self.max_summary_words = max(max_summary_words, self.min_summary_words)
        self.logger = get_logger("layer2.memory.summarizer")

    @staticmethod
    def _format_steps(steps: List[Dict[str, Any]], result_snippet_len: int = RESULT_SNIPPET_MAX_LEN) -> str:
        """Форматирует шаги в текст для промпта."""
        lines = []
        for i, step in enumerate(steps):
            agent_type = step.get("agent_type", "unknown")
            action = step.get("action", "unknown")
            result = step.get("result")
            snippet = ""
            if isinstance(result, dict):
                if result.get("error"):
                    snippet = str(result.get("error", ""))[:result_snippet_len]
                elif result.get("content"):
                    snippet = str(result.get("content", ""))[:result_snippet_len]
                elif result:
                    snippet = str(result)[:result_snippet_len]
            elif result is not None:
                snippet = str(result)[:result_snippet_len]
            if snippet and len(snippet) == result_snippet_len:
                snippet += "..."
            lines.append(f"Step {i + 1} [{agent_type}] {action}:\n  Result: {snippet or '(no output)'}")
        return "\n\n".join(lines)

    def _build_prompt(self, steps_text: str) -> str:
        """Строит полный промпт с инструкциями и few-shot."""
        return (
            SYSTEM_PROMPT
            + FEW_SHOT
            + f"\nConversation to summarize:\n\n{steps_text}\n\nSummary:"
        )

    async def _call_llm(self, prompt: str) -> str:
        """Вызывает LLM и возвращает полный текст ответа."""
        content_parts: List[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts).strip()

    def _truncate_to_word_limit(self, text: str, max_words: int) -> str:
        """Обрезает текст до max_words слов."""
        words = (text or "").split()
        if len(words) <= max_words:
            return text.strip()
        return " ".join(words[:max_words]).strip()

    async def summarize(self, steps: List[Dict[str, Any]]) -> str:
        """
        Суммаризирует историю шагов диалога.

        Args:
            steps: Список шагов из EpisodicMemory (step_id, agent_type, action, result, metadata).

        Returns:
            Краткое резюме строкой.
        """
        if not self.enabled:
            return ""

        if not steps:
            return ""

        steps_to_use = steps[: self.max_input_steps]
        steps_text = self._format_steps(steps_to_use)
        prompt = self._build_prompt(steps_text)

        try:
            raw = await self._call_llm(prompt)
            summary = self._truncate_to_word_limit(raw, self.max_summary_words)
            self.logger.debug("Summarized %d steps into %d words", len(steps_to_use), len(summary.split()))
            return summary
        except Exception as exc:
            self.logger.warning("Conversation summarization failed: %s", exc)
            return ""
