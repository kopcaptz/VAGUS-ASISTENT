"""
CoherenceMonitor — заглушка для отслеживания размера контекста.
В Шаге 3.4: вызов ConversationSummarizer при превышении порога.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .episodic import EpisodicMemory
    from .summarizer import ConversationSummarizer


class CoherenceMonitor:
    """
    Заглушка. В Шаге 3.4: отслеживание размера контекста,
    вызов summarizer при пороге, замена старых шагов на резюме.
    """

    def __init__(
        self,
        summarizer: Optional["ConversationSummarizer"] = None,
        threshold_steps: int = 10,
    ) -> None:
        self.summarizer = summarizer
        self.threshold_steps = max(1, threshold_steps)

    async def should_summarize(self, step_count: int) -> bool:
        """Возвращает True если число шагов >= порога и summarizer включён."""
        if not self.summarizer or not self.summarizer.enabled:
            return False
        return step_count >= self.threshold_steps

    async def summarize_and_replace(
        self,
        task_id: str,
        memory: "EpisodicMemory",
    ) -> str:
        """
        Placeholder: возвращает пустую строку.
        В Шаге 3.4: получить историю, суммаризировать, заменить старые шаги.
        """
        return ""
