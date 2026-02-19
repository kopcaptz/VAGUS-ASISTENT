"""
Конфигурация цепочек fallback провайдеров.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from ...layer0.logging import get_logger


@dataclass
class FallbackChain:
    """Цепочка провайдеров для fallback."""

    provider_ids: List[str] = field(default_factory=list)
    name: str = "default"

    def __post_init__(self) -> None:
        self.logger = get_logger("fallback.chain")
        if not self.provider_ids:
            self.logger.warning("FallbackChain created with empty provider list")

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "FallbackChain":
        """
        Создаёт цепочку из конфигурации.

        Args:
            config: Словарь с ключами:
                - chains: dict of {name: [provider_ids]}
                - default_chain: имя цепочки по умолчанию
                Или простой список: [provider_id1, provider_id2]

        Returns:
            FallbackChain
        """
        if isinstance(config, list):
            return cls(provider_ids=list(config))

        chains = config.get("chains", {})
        default_name = config.get("default_chain", "default")
        chain_ids = chains.get(default_name, config.get("providers", []))

        if isinstance(chain_ids, str):
            chain_ids = [chain_ids]

        return cls(provider_ids=list(chain_ids), name=default_name)

    def get_providers(self) -> List[str]:
        """Возвращает список ID провайдеров в порядке приоритета."""
        return list(self.provider_ids)
