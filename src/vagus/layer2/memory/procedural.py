"""
ProceduralMemory — хранилище успешных планов задач для переиспользования.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import aiosqlite

from ...layer0.logging import get_logger

if TYPE_CHECKING:
    from ..intent_classifier import IntentResult
    from ..planning import TaskPlan


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS procedural_plans (
    plan_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    intent_summary TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    success_score REAL DEFAULT 0.5,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_created_at ON procedural_plans(created_at);
"""

CREATE_INDEX_TENANT_SQL = """
CREATE INDEX IF NOT EXISTS idx_procedural_tenant ON procedural_plans(tenant_id);
"""


def intent_to_summary(intent: "IntentResult") -> str:
    """
    Преобразует IntentResult в строку для поиска и хранения.
    """
    primary = intent.get("primary_intent", "mixed") or "mixed"
    sub_intents = intent.get("sub_intents") or []
    entities = intent.get("entities") or {}
    complexity = intent.get("complexity", "moderate") or "moderate"

    parts = [primary]
    if sub_intents:
        parts.extend(str(s) for s in sub_intents)
    for k, v in entities.items():
        parts.append(f"{k}={v}")
    parts.append(complexity)
    return " ".join(str(p) for p in parts).strip()


def _similarity(a: str, b: str) -> float:
    """
    Jaccard similarity по множествам слов.
    """
    wa = set((a or "").lower().split())
    wb = set((b or "").lower().split())
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


class ProceduralMemory:
    """
    SQLite-backed хранилище успешных планов задач.
    Позволяет искать похожие планы по intent_summary для переиспользования.
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        enabled: bool = True,
    ) -> None:
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self.enabled = enabled
        self.logger = get_logger("layer2.memory.procedural")

    async def _ensure_conn(self) -> aiosqlite.Connection:
        """Lazy connect при первом вызове."""
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute(CREATE_TABLE_SQL)
            await self._conn.execute(CREATE_INDEX_SQL)
            await self._conn.execute(CREATE_INDEX_TENANT_SQL)
            await self._conn.commit()
            self.logger.debug("ProceduralMemory connected to %s", self.db_path)
        return self._conn

    async def save_plan(
        self,
        tenant_id: Union[str, "TaskPlan"],
        intent_summary: str,
        plan_json: str = "",
        success_score: float = 0.5,
    ) -> str:
        """
        Сохраняет план в базу.
        Генерирует plan_id как UUID4.
        Возвращает plan_id.

        Args:
            tenant_id: Идентификатор tenant (или plan dict для backward compat).
            intent_summary: Краткое описание намерения.
            plan_json: JSON-строка плана (или пустая при backward compat).
            success_score: Оценка успешности 0..1.

        Backward compat: save_plan(plan, intent_summary, success_score) — первый
        аргумент dict трактуется как plan, tenant_id="default".
        """
        if not self.enabled:
            return ""

        if isinstance(tenant_id, dict):
            plan = dict(tenant_id)
            plan_json = json.dumps(plan, ensure_ascii=False, default=str)
            tenant_id = "default"

        conn = await self._ensure_conn()
        plan_id = uuid.uuid4().hex
        success_score = max(0.0, min(1.0, success_score))

        await conn.execute(
            """
            INSERT INTO procedural_plans (plan_id, tenant_id, intent_summary, plan_json, success_score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (plan_id, str(tenant_id), intent_summary, plan_json, success_score),
        )
        await conn.commit()
        self.logger.debug("Saved plan %s with intent_summary=%s", plan_id, intent_summary[:50])
        return plan_id

    async def find_similar_plan(
        self,
        tenant_id: Union[str, "IntentResult"],
        intent_summary: str = "",
        threshold: float = 0.7,
    ) -> Optional[Dict[str, Any]]:
        """
        Ищет похожий план по intent_summary (простой текстовый поиск Jaccard).
        Фильтрует по tenant_id. Возвращает план с наибольшим success_score.

        Backward compat: find_similar_plan(intent, threshold) — первый аргумент
        dict трактуется как IntentResult, tenant_id="default".
        """
        if not self.enabled:
            return None

        if isinstance(tenant_id, dict):
            intent_summary = intent_to_summary(tenant_id)
            tenant_id = "default"

        conn = await self._ensure_conn()
        if not (intent_summary or "").strip():
            return None

        async with conn.execute(
            """
            SELECT plan_id, tenant_id, intent_summary, plan_json, success_score, usage_count
            FROM procedural_plans
            WHERE tenant_id = ?
            """,
            (str(tenant_id),),
        ) as cursor:
            rows = await cursor.fetchall()

        candidates: List[tuple[float, float, Dict[str, Any]]] = []

        for row in rows:
            stored_plan_id, stored_tenant, stored_summary, plan_json_str, success_score, usage_count = row
            sim = _similarity(intent_summary, stored_summary or "")
            if sim < threshold:
                continue

            rank = float(success_score or 0.5) * (1.0 + 0.1 * (usage_count or 0))
            try:
                plan_data = json.loads(plan_json_str)
                if isinstance(plan_data, dict):
                    plan_data["plan_id"] = stored_plan_id
                    candidates.append((sim, rank, plan_data))
            except (json.JSONDecodeError, TypeError):
                continue

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidates[0][2]

    async def increment_usage(self, plan_id: str, tenant_id: str) -> None:
        """
        Увеличивает usage_count на 1 для плана.
        Обновляет только если plan_id и tenant_id совпадают.
        """
        if not self.enabled:
            return

        conn = await self._ensure_conn()
        await conn.execute(
            """
            UPDATE procedural_plans SET usage_count = usage_count + 1
            WHERE plan_id = ? AND tenant_id = ?
            """,
            (plan_id, tenant_id),
        )
        await conn.commit()
        self.logger.debug("Incremented usage_count for plan %s (tenant=%s)", plan_id, tenant_id)

    async def increment_usage_count(self, plan_id: str) -> None:
        """Backward compat: вызывает increment_usage(plan_id, "default")."""
        await self.increment_usage(plan_id, "default")

    async def get_plan(self, plan_id: str) -> Optional["TaskPlan"]:
        """Получает план по ID. plan_id в результате — DB key (может отличаться от JSON)."""
        if not self.enabled:
            return None

        conn = await self._ensure_conn()
        async with conn.execute(
            "SELECT plan_json FROM procedural_plans WHERE plan_id = ?",
            (plan_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        try:
            data = json.loads(row[0])
            if not isinstance(data, dict) or "steps" not in data:
                return None
            data["plan_id"] = plan_id
            return data
        except (json.JSONDecodeError, TypeError):
            return None

    async def get_all_plans(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Возвращает список планов с метаданными.
        Формат: [{"plan_id", "intent_summary", "success_score", "created_at", "usage_count"}]
        """
        if not self.enabled:
            return []

        conn = await self._ensure_conn()
        async with conn.execute(
            """
            SELECT plan_id, intent_summary, success_score, created_at, usage_count
            FROM procedural_plans
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, limit),),
        ) as cursor:
            rows = await cursor.fetchall()

        return [
            {
                "plan_id": r[0],
                "intent_summary": r[1],
                "success_score": r[2],
                "created_at": r[3],
                "usage_count": r[4],
            }
            for r in rows
        ]

    async def close(self) -> None:
        """Закрывает соединение с БД."""
        if self._conn:
            await self._conn.close()
            self._conn = None
            self.logger.debug("ProceduralMemory connection closed")
