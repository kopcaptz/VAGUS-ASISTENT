"""
Базовый класс стратегии балансировки провайдеров.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List


class BaseBalancingStrategy(ABC):
    """Абстрактная стратегия выбора провайдера."""

    @abstractmethod
    def select_provider(
        self,
        providers: Dict[str, Any],
        request_context: Dict[str, Any],
    ) -> str:
        """
        Выбирает провайдера по стратегии.

        Args:
            providers: Словарь {provider_id: provider_info}
                provider_info может содержать: cost, latency, quality, provider_obj
            request_context: Контекст запроса: priority, interactive, stream, model, etc.

        Returns:
            provider_id выбранного провайдера

        Raises:
            ValueError: Если нет доступных провайдеров
        """
        pass
