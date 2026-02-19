"""
Обработчик и валидация входящих запросов.
"""

from typing import Dict, Any, Optional
from ..providers.base_provider import LLMRequest


class RequestHandler:
    """Парсинг и валидация запросов в LLMRequest."""

    def parse(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        priority: str = "normal",
        interactive: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> LLMRequest:
        """
        Создаёт LLMRequest из параметров.

        Args:
            prompt: Текст запроса
            model: Модель (опционально)
            temperature: Температура
            max_tokens: Максимум токенов
            stream: Режим стриминга
            priority: urgent | normal | low
            interactive: Интерактивный режим
            metadata: Дополнительные метаданные

        Returns:
            LLMRequest
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")
        if priority not in ("urgent", "normal", "low"):
            priority = "normal"
        return LLMRequest(
            prompt=prompt.strip(),
            model=model,
            temperature=max(0, min(2, temperature)),
            max_tokens=max(1, min(100000, max_tokens)),
            stream=stream,
            priority=priority,
            interactive=interactive,
            metadata=metadata or {},
        )
