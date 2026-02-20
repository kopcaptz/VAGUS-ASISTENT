"""
Базовый класс для всех специализированных агентов.
Все LLM-вызовы проходят через LLMRouter (Слой 1).
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ...layer0.logging import get_logger
from ..types import AgentContext, AgentResult, AgentTask
from .protocols import LLMRouterProtocol


class BaseAgent(ABC):
    """
    Абстрактный агент — рабочая лошадка системы.
    Каждый специализированный агент (Researcher, Coder, Analyst) наследует этот класс.
    """

    def __init__(
        self,
        name: str,
        llm_router: LLMRouterProtocol,
        description: str = "",
    ):
        """
        Args:
            name: Идентификатор агента (researcher, coder, analyst, ...)
            llm_router: LLMRouter из Слоя 1 для всех LLM-вызовов
            description: Описание роли агента
        """
        self.name = name
        self.llm_router = llm_router
        self.description = description
        self.logger = get_logger(f"layer2.agent.{name}")

    @abstractmethod
    async def process(
        self,
        task: AgentTask,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        """
        Обрабатывает задачу. Должен быть реализован в подклассах.

        Args:
            task: Словарь с полями (prompt, task_type, ...)
            context: Дополнительный контекст (результаты предыдущих шагов)

        Returns:
            Результат обработки (content, metadata, ...)
        """
        pass

    def can_handle(self, task_type: str) -> bool:
        """
        Проверяет, может ли агент обработать данный тип задачи.
        Переопределить в подклассах.
        """
        return False

    def is_available(self) -> bool:
        """Health-check hook for orchestrator graceful degradation."""
        return True
