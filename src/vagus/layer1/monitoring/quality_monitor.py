"""
Монитор качества ответов LLM.
Базовая оценка на основе эвристик; интерфейс расширяемый.
"""

from typing import Dict, Any, Optional
from ...layer0.logging import get_logger


class QualityMonitor:
    """Монитор качества ответов."""

    def __init__(self):
        self.logger = get_logger("monitoring.quality_monitor")

    def evaluate(
        self,
        content: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Оценивает качество ответа по шкале [0, 1].

        Базовая эвристика: длина ответа и количество токенов.
        Может быть расширена (модель качества, пользовательские метрики).

        Args:
            content: Текст ответа
            prompt_tokens: Токены промпта
            completion_tokens: Токены ответа
            metadata: Дополнительные метаданные

        Returns:
            Оценка качества от 0 до 1
        """
        if not content and completion_tokens == 0:
            return 0.0

        # Простая эвристика: наличие контента + длина
        has_content = 1.0 if content and len(content.strip()) > 0 else 0
        length_score = min(1.0, len(content) / 500) if content else 0  # 500+ символов = 1
        token_score = min(1.0, completion_tokens / 100) if completion_tokens else 0.5

        score = (has_content * 0.5 + length_score * 0.25 + token_score * 0.25)
        return round(min(1.0, max(0.0, score)), 2)
