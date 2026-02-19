"""
Интеграция логирования через layer0.logging.
"""

from typing import Any
from ...layer0.logging import get_logger, configure_from_config


def setup_logging(config: Any = None) -> None:
    """
    Настраивает логирование из конфигурации.

    Args:
        config: AppConfig или None
    """
    configure_from_config(config)
