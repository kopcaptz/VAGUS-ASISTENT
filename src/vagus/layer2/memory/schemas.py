"""
Pydantic-модели для MemoryManager и ArtifactKnowledgeBase.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryEntry(BaseModel):
    """Запись в памяти."""

    id: str
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: Optional[datetime] = None


class ArtifactRecord(BaseModel):
    """Артефакт для базы знаний (код, документы, результаты)."""

    id: str
    artifact_type: str = Field(..., description="Тип артефакта: code, document, result, etc.")
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
    task_id: Optional[str] = None
    agent_type: Optional[str] = None


class ArtifactSearchResult(BaseModel):
    """Результат поиска артефакта."""

    artifact: ArtifactRecord
    score: float = 0.0
