"""Абстрактный интерфейс ArtifactKnowledgeBase."""
from typing import Optional, Protocol


class ArtifactKnowledgeBaseProtocol(Protocol):
    """Protocol для ArtifactKnowledgeBase — структурная типизация без наследования."""

    async def write_artifact(
        self,
        content: str,
        artifact_type: str,
        source: str,
        tenant_id: str,
        plan_id: str = "default",
        key: str = "default",
        agent_type: str = "unknown",
        session_id: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> str:
        """Создать артефакт и сохранить. Возвращает artifact_id."""
        ...

    async def link_artifacts(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        rel_type: str = "derived_from",
    ) -> None:
        """Связать два артефакта."""
        ...

    async def strengthen_connection(
        self,
        source_id: str,
        target_id: str,
        score: float,
        tenant_id: str,
    ) -> None:
        """Усилить связь между артефактами."""
        ...

    async def weaken_connection(
        self,
        artifact_id: str,
        penalty: float,
        tenant_id: str,
    ) -> None:
        """Ослабить все связи, где artifact_id — source или target."""
        ...
