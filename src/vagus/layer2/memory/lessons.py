"""
LessonsMemory — PostgreSQL backend для хранения уроков рефлексии.
Сохраняет опыт циклов самокоррекции для повторного использования.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, List, Optional, Dict
from datetime import datetime, timezone

from ...layer0.logging import get_logger
from .schemas import LessonSchema, LessonSearchResult


def _pg_url(url: str) -> str:
    """Преобразует postgresql+asyncpg:// в postgresql:// для asyncpg."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _hash_prompt(prompt: str) -> str:
    """Возвращает SHA-256 хеш промпта."""
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


class LessonsMemory:
    """
    PostgreSQL backend для хранения уроков рефлексии.
    Требует выполненной миграции alembic (таблица lessons).
    """

    def __init__(
        self,
        postgres_url: str,
        *,
        min_size: int = 2,
        max_size: int = 10,
        fallback_enabled: bool = True,
        fallback_max_entries: int = 1000,
    ) -> None:
        self._postgres_url = _pg_url(postgres_url)
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None
        self.logger = get_logger("layer2.memory.lessons")
        self._fallback_enabled = fallback_enabled
        self._fallback_max_entries = fallback_max_entries
        self._in_memory_lessons: Dict[str, List[Dict]] = {}  # tenant_id -> list of lessons
        self._using_fallback = False

    async def _ensure_pool(self) -> None:
        """Ленивая инициализация пула соединений."""
        if self._pool is not None:
            return
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError("asyncpg is not installed") from exc
        try:
            self._pool = await asyncpg.create_pool(
                self._postgres_url,
                min_size=self._min_size,
                max_size=self._max_size,
            )
            self.logger.info("LessonsMemory pool created")
            self._using_fallback = False
        except Exception as exc:
            self.logger.warning(
                "Cannot connect to PostgreSQL for LessonsMemory: %s. Using in‑memory fallback.",
                exc,
            )
            self._pool = None
            self._using_fallback = True
            if not self._fallback_enabled:
                raise

    async def close(self) -> None:
        """Закрыть пул соединений."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self.logger.debug("LessonsMemory pool closed")

    async def save_lesson(
        self,
        tenant_id: str,
        original_prompt: str,
        agent_type: str,
        issues: str,
        suggestions: str,
        refined_prompt: str,
        score_before: float,
        score_after: float,
    ) -> str:
        """
        Сохранить урок рефлексии.
        Возвращает ID урока.
        """
        lesson_id = str(uuid.uuid4())
        prompt_hash = _hash_prompt(original_prompt)
        created_at = datetime.now(timezone.utc).isoformat()

        await self._ensure_pool()

        # Если пул не создан (PostgreSQL недоступен) и включен fallback
        if self._pool is None and self._fallback_enabled:
            lesson = {
                "id": lesson_id,
                "tenant_id": tenant_id,
                "original_prompt_hash": prompt_hash,
                "agent_type": agent_type,
                "issues": issues,
                "suggestions": suggestions,
                "refined_prompt": refined_prompt,
                "score_before": score_before,
                "score_after": score_after,
                "created_at": created_at,
            }
            if tenant_id not in self._in_memory_lessons:
                self._in_memory_lessons[tenant_id] = []
            self._in_memory_lessons[tenant_id].append(lesson)
            # Ограничиваем размер
            if len(self._in_memory_lessons[tenant_id]) > self._fallback_max_entries:
                self._in_memory_lessons[tenant_id].pop(0)
            self.logger.debug("Lesson saved in‑memory, tenant=%s, agent=%s", tenant_id, agent_type)
            return lesson_id

        # Сохраняем в PostgreSQL
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO lessons (
                        id, tenant_id, original_prompt_hash, agent_type,
                        issues, suggestions, refined_prompt,
                        score_before, score_after, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    lesson_id,
                    tenant_id,
                    prompt_hash,
                    agent_type,
                    issues,
                    suggestions,
                    refined_prompt,
                    score_before,
                    score_after,
                    created_at,
                )
            self.logger.debug("Lesson saved in PostgreSQL, tenant=%s, agent=%s", tenant_id, agent_type)
            return lesson_id
        except Exception as exc:
            self.logger.error("Failed to save lesson in PostgreSQL: %s", exc)
            if self._fallback_enabled:
                # Fallback to in‑memory
                lesson = {
                    "id": lesson_id,
                    "tenant_id": tenant_id,
                    "original_prompt_hash": prompt_hash,
                    "agent_type": agent_type,
                    "issues": issues,
                    "suggestions": suggestions,
                    "refined_prompt": refined_prompt,
                    "score_before": score_before,
                    "score_after": score_after,
                    "created_at": created_at,
                }
                if tenant_id not in self._in_memory_lessons:
                    self._in_memory_lessons[tenant_id] = []
                self._in_memory_lessons[tenant_id].append(lesson)
                if len(self._in_memory_lessons[tenant_id]) > self._fallback_max_entries:
                    self._in_memory_lessons[tenant_id].pop(0)
                self.logger.debug("Lesson saved in‑memory after PostgreSQL failure")
                return lesson_id
            raise

    async def find_similar_lessons(
        self,
        tenant_id: str,
        original_prompt: str,
        agent_type: str,
        limit: int = 5,
    ) -> List[LessonSearchResult]:
        """
        Найти похожие уроки по хешу промпта и типу агента.
        Возвращает список уроков с оценкой схожести.
        """
        prompt_hash = _hash_prompt(original_prompt)
        await self._ensure_pool()

        # Если пул не создан и есть in‑memory fallback
        if self._pool is None and self._fallback_enabled:
            results: List[LessonSearchResult] = []
            if tenant_id in self._in_memory_lessons:
                for lesson in self._in_memory_lessons[tenant_id]:
                    if lesson["agent_type"] == agent_type and lesson["original_prompt_hash"] == prompt_hash:
                        schema = LessonSchema(**lesson)
                        results.append(LessonSearchResult(lesson=schema, similarity_score=1.0))
            return results[:limit]

        # Ищем в PostgreSQL
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT * FROM lessons
                       WHERE tenant_id = $1
                         AND agent_type = $2
                         AND original_prompt_hash = $3
                       ORDER BY created_at DESC
                       LIMIT $4""",
                    tenant_id,
                    agent_type,
                    prompt_hash,
                    limit,
                )
            results = []
            for row in rows:
                schema = LessonSchema(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    original_prompt_hash=row["original_prompt_hash"],
                    agent_type=row["agent_type"],
                    issues=row["issues"],
                    suggestions=row["suggestions"],
                    refined_prompt=row["refined_prompt"],
                    score_before=row["score_before"],
                    score_after=row["score_after"],
                    created_at=row["created_at"],
                )
                results.append(LessonSearchResult(lesson=schema, similarity_score=1.0))
            return results
        except Exception as exc:
            self.logger.error("Failed to query lessons from PostgreSQL: %s", exc)
            if self._fallback_enabled:
                # Fallback to in‑memory
                results = []
                if tenant_id in self._in_memory_lessons:
                    for lesson in self._in_memory_lessons[tenant_id]:
                        if lesson["agent_type"] == agent_type and lesson["original_prompt_hash"] == prompt_hash:
                            schema = LessonSchema(**lesson)
                            results.append(LessonSearchResult(lesson=schema, similarity_score=1.0))
                return results[:limit]
            raise

    async def get_lessons_by_agent(
        self,
        tenant_id: str,
        agent_type: str,
        limit: int = 10,
    ) -> List[LessonSchema]:
        """
        Получить последние уроки для данного типа агента.
        """
        await self._ensure_pool()
        if self._pool is None and self._fallback_enabled:
            lessons = []
            if tenant_id in self._in_memory_lessons:
                for lesson in self._in_memory_lessons[tenant_id]:
                    if lesson["agent_type"] == agent_type:
                        lessons.append(LessonSchema(**lesson))
            lessons.sort(key=lambda x: x.created_at, reverse=True)
            return lessons[:limit]

        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT * FROM lessons
                       WHERE tenant_id = $1 AND agent_type = $2
                       ORDER BY created_at DESC
                       LIMIT $3""",
                    tenant_id,
                    agent_type,
                    limit,
                )
            return [
                LessonSchema(
                    id=row["id"],
                    tenant_id=row["tenant_id"],
                    original_prompt_hash=row["original_prompt_hash"],
                    agent_type=row["agent_type"],
                    issues=row["issues"],
                    suggestions=row["suggestions"],
                    refined_prompt=row["refined_prompt"],
                    score_before=row["score_before"],
                    score_after=row["score_after"],
                    created_at=row["created_at"],
                ) for row in rows
            ]
        except Exception as exc:
            self.logger.error("Failed to query lessons by agent: %s", exc)
            if self._fallback_enabled:
                lessons = []
                if tenant_id in self._in_memory_lessons:
                    for lesson in self._in_memory_lessons[tenant_id]:
                        if lesson["agent_type"] == agent_type:
                            lessons.append(LessonSchema(**lesson))
                lessons.sort(key=lambda x: x.created_at, reverse=True)
                return lessons[:limit]
            raise

    def is_using_fallback(self) -> bool:
        """Возвращает True, если используется in‑memory fallback."""
        return self._using_fallback
