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


class LessonSchema(BaseModel):
    """Схема для хранения урока рефлексии."""

    id: str
    tenant_id: str = Field(..., description="Идентификатор tenant для изоляции")
    original_prompt_hash: str = Field(..., description="SHA-256 хеш оригинального промпта")
    agent_type: str = Field(..., description="Тип агента (Researcher, Coder, Analyst, ...)")
    issues: str = Field(..., description="Выявленные проблемы (JSON или текст)")
    suggestions: str = Field(..., description="Предложения по улучшению (JSON или текст)")
    refined_prompt: str = Field(..., description="Улучшенный промпт после рефлексии")
    score_before: float = Field(..., description="Оценка до рефлексии")
    score_after: float = Field(..., description="Оценка после рефлексии")
    created_at: datetime = Field(default_factory=_utc_now)


class LessonSearchResult(BaseModel):
    """Результат поиска урока."""

    lesson: LessonSchema
    similarity_score: float = 0.0  # Для будущего семантического поиска
