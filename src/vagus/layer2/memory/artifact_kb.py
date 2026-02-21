"""
ArtifactKnowledgeBase — база знаний артефактов (код, документы, результаты работы агентов).
Реализует ArtifactKnowledgeBaseProtocol.
"""

import json
import uuid
from typing import List, Optional

import aiosqlite

from .exceptions import ArtifactNotFoundError
from .schemas import ArtifactRecord, ArtifactSearchResult


CREATE_ARTIFACTS_TABLE = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    key TEXT NOT NULL,
    content_json TEXT NOT NULL,
    artifact_type TEXT,
    agent_type TEXT,
    session_id TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ttl_seconds INTEGER
);
"""

CREATE_RELATIONSHIPS_TABLE = """
CREATE TABLE IF NOT EXISTS artifact_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_id, target_id, tenant_id),
    FOREIGN KEY (source_id) REFERENCES artifacts(artifact_id),
    FOREIGN KEY (target_id) REFERENCES artifacts(artifact_id)
);
"""

CREATE_INDEX_ARTIFACTS_TENANT = (
    "CREATE INDEX IF NOT EXISTS idx_artifacts_tenant ON artifacts(tenant_id);"
)
CREATE_INDEX_RELATIONSHIPS_TENANT = (
    "CREATE INDEX IF NOT EXISTS idx_relationships_tenant ON artifact_relationships(tenant_id);"
)


class ArtifactKnowledgeBase:
    """
    Хранилище артефактов с возможностью семантического поиска.
    Артефакты: фрагменты кода, документы, результаты анализа и т.п.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        """
        Инициализация ArtifactKnowledgeBase.

        Args:
            db_path: Путь к SQLite (по умолчанию in-memory).
        """
        self._db_path = db_path
        self._initialized = False
        self._conn: Optional[aiosqlite.Connection] = None

    async def _init_db(self, conn: aiosqlite.Connection) -> None:
        """Создание таблиц и индексов при инициализации."""
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute(CREATE_ARTIFACTS_TABLE)
        await conn.execute(CREATE_RELATIONSHIPS_TABLE)
        await conn.execute(CREATE_INDEX_ARTIFACTS_TENANT)
        await conn.execute(CREATE_INDEX_RELATIONSHIPS_TENANT)
        await conn.commit()

    async def _ensure_initialized(self) -> None:
        """Инициализация БД при первом обращении."""
        if self._initialized:
            return
        conn = await aiosqlite.connect(self._db_path)
        await self._init_db(conn)
        self._conn = conn
        self._initialized = True

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
        """
        Создать артефакт и сохранить в БД.

        Returns:
            artifact_id — сгенерированный UUID4 идентификатор.
        """
        await self._ensure_initialized()
        artifact_id = str(uuid.uuid4())
        content_json = json.dumps({"content": content})
        await self._conn.execute(
            """INSERT INTO artifacts (
                artifact_id, tenant_id, plan_id, key, content_json,
                artifact_type, agent_type, session_id, source, ttl_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id,
                tenant_id,
                plan_id,
                key,
                content_json,
                artifact_type,
                agent_type,
                session_id,
                source,
                ttl_seconds,
            ),
        )
        await self._conn.commit()
        return artifact_id

    async def _artifact_exists(self, artifact_id: str, tenant_id: str) -> bool:
        """Проверка существования артефакта по id и tenant."""
        await self._ensure_initialized()
        async with self._conn.execute(
            "SELECT 1 FROM artifacts WHERE artifact_id = ? AND tenant_id = ?",
            (artifact_id, tenant_id),
        ) as cur:
            row = await cur.fetchone()
        return row is not None

    async def get_artifact_id_by_plan_key(
        self,
        tenant_id: str,
        plan_id: str,
        key: str,
    ) -> Optional[str]:
        """Получить artifact_id по tenant_id, plan_id и key. None если не найден."""
        await self._ensure_initialized()
        async with self._conn.execute(
            "SELECT artifact_id FROM artifacts WHERE tenant_id = ? AND plan_id = ? AND key = ?",
            (tenant_id, plan_id, key),
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def link_artifacts(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        rel_type: str = "derived_from",
    ) -> None:
        """Связать два артефакта. Дубликаты игнорируются."""
        await self._ensure_initialized()
        if not await self._artifact_exists(source_id, tenant_id):
            raise ArtifactNotFoundError(source_id)
        if not await self._artifact_exists(target_id, tenant_id):
            raise ArtifactNotFoundError(target_id)
        await self._conn.execute(
            """INSERT OR IGNORE INTO artifact_relationships
               (tenant_id, source_id, target_id, rel_type, weight)
               VALUES (?, ?, ?, ?, 0.5)""",
            (tenant_id, source_id, target_id, rel_type),
        )
        await self._conn.commit()

    async def _get_connection_weight(
        self, source_id: str, target_id: str, tenant_id: str
    ) -> Optional[float]:
        """Получить текущий вес связи. Возвращает None, если связь не существует."""
        await self._ensure_initialized()
        async with self._conn.execute(
            """SELECT weight FROM artifact_relationships
               WHERE source_id = ? AND target_id = ? AND tenant_id = ?""",
            (source_id, target_id, tenant_id),
        ) as cur:
            row = await cur.fetchone()
        return float(row[0]) if row is not None else None

    async def strengthen_connection(
        self,
        source_id: str,
        target_id: str,
        score: float,
        tenant_id: str,
    ) -> None:
        """Усилить связь между артефактами. Создаёт связь, если её нет."""
        await self._ensure_initialized()
        weight = await self._get_connection_weight(source_id, target_id, tenant_id)
        delta = 0.1 * score
        if weight is None:
            if not await self._artifact_exists(source_id, tenant_id):
                raise ArtifactNotFoundError(source_id)
            if not await self._artifact_exists(target_id, tenant_id):
                raise ArtifactNotFoundError(target_id)
            new_weight = min(1.0, 0.5 + delta)
            await self._conn.execute(
                """INSERT INTO artifact_relationships
                   (tenant_id, source_id, target_id, rel_type, weight)
                   VALUES (?, ?, ?, 'derived_from', ?)""",
                (tenant_id, source_id, target_id, new_weight),
            )
        else:
            new_weight = min(1.0, weight + delta)
            await self._conn.execute(
                """UPDATE artifact_relationships
                   SET weight = ? WHERE source_id = ? AND target_id = ? AND tenant_id = ?""",
                (new_weight, source_id, target_id, tenant_id),
            )
        await self._conn.commit()

    async def weaken_connection(
        self,
        artifact_id: str,
        penalty: float,
        tenant_id: str,
    ) -> None:
        """Ослабить все связи, где artifact_id — source или target."""
        await self._ensure_initialized()
        delta = 0.1 * penalty
        await self._conn.execute(
            """UPDATE artifact_relationships
               SET weight = max(0.0, weight - ?)
               WHERE (source_id = ? OR target_id = ?) AND tenant_id = ?""",
            (delta, artifact_id, artifact_id, tenant_id),
        )
        await self._conn.commit()

    async def strengthen_connections_batch(
        self, updates: List[dict], tenant_id: str
    ) -> None:
        """
        Пакетное усиление связей. executemany для INSERT и UPDATE.
        updates: [{"source_id": str, "target_id": str, "score": float}, ...]
        """
        if not updates:
            return
        await self._ensure_initialized()

        artifact_ids = set()
        for u in updates:
            sid = u.get("source_id")
            tid = u.get("target_id")
            if not sid or not tid:
                raise ArtifactNotFoundError(str(sid or tid or "unknown"))
            artifact_ids.add(sid)
            artifact_ids.add(tid)
        for aid in artifact_ids:
            if not await self._artifact_exists(aid, tenant_id):
                raise ArtifactNotFoundError(aid)

        weight_map: dict[tuple[str, str], float] = {}
        if len(updates) <= 50:
            or_parts = []
            params = [tenant_id]
            for u in updates:
                or_parts.append("(source_id = ? AND target_id = ?)")
                params.extend([u["source_id"], u["target_id"]])
            placeholders = " OR ".join(or_parts)
            async with self._conn.execute(
                f"""SELECT source_id, target_id, weight FROM artifact_relationships
                    WHERE tenant_id = ? AND ({placeholders})""",
                params,
            ) as cur:
                async for row in cur:
                    weight_map[(row[0], row[1])] = float(row[2])
        else:
            for u in updates:
                w = await self._get_connection_weight(
                    u["source_id"], u["target_id"], tenant_id
                )
                if w is not None:
                    weight_map[(u["source_id"], u["target_id"])] = w

        insert_params: List[tuple] = []
        update_params: List[tuple] = []

        for u in updates:
            sid = u["source_id"]
            tid = u["target_id"]
            score = float(u.get("score", 1.0))
            delta = 0.1 * score
            key = (sid, tid)
            weight = weight_map.get(key)
            if weight is None:
                new_weight = min(1.0, 0.5 + delta)
                insert_params.append((tenant_id, sid, tid, new_weight))
            else:
                new_weight = min(1.0, weight + delta)
                update_params.append((new_weight, sid, tid, tenant_id))

        if insert_params:
            await self._conn.executemany(
                """INSERT INTO artifact_relationships
                   (tenant_id, source_id, target_id, rel_type, weight)
                   VALUES (?, ?, ?, 'derived_from', ?)""",
                insert_params,
            )
        if update_params:
            await self._conn.executemany(
                """UPDATE artifact_relationships
                   SET weight = ? WHERE source_id = ? AND target_id = ? AND tenant_id = ?""",
                update_params,
            )
        await self._conn.commit()

    async def get_relationships_for_graph(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        """
        Получить связи для визуализации графа.
        Returns: [{"source_id": str, "target_id": str, "weight": float}, ...]
        """
        await self._ensure_initialized()
        if tenant_id is not None:
            async with self._conn.execute(
                """SELECT source_id, target_id, weight FROM artifact_relationships
                   WHERE tenant_id = ? LIMIT ?""",
                (tenant_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with self._conn.execute(
                """SELECT source_id, target_id, weight FROM artifact_relationships
                   LIMIT ?""",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            {"source_id": row[0], "target_id": row[1], "weight": float(row[2])}
            for row in rows
        ]

    async def weaken_connections_batch(
        self, updates: List[dict], tenant_id: str
    ) -> None:
        """
        Пакетное ослабление связей. executemany для UPDATE.
        updates: [{"artifact_id": str, "penalty": float}, ...]
        """
        if not updates:
            return
        await self._ensure_initialized()

        params_list = []
        for u in updates:
            aid = u.get("artifact_id")
            penalty = float(u.get("penalty", 1.0))
            delta = 0.1 * penalty
            params_list.append((delta, aid, aid, tenant_id))

        await self._conn.executemany(
            """UPDATE artifact_relationships
               SET weight = max(0.0, weight - ?)
               WHERE (source_id = ? OR target_id = ?) AND tenant_id = ?""",
            params_list,
        )
        await self._conn.commit()

    async def add(self, artifact: ArtifactRecord) -> None:
        """
        Добавить артефакт в базу знаний.

        Args:
            artifact: Артефакт для сохранения.
        """
        await self._ensure_initialized()
        # TODO: сохранение в SQLite + векторизация для семантического поиска
        raise NotImplementedError("ArtifactKnowledgeBase.add — в разработке")

    async def search(
        self,
        query: str,
        artifact_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[ArtifactSearchResult]:
        """
        Семантический поиск артефактов по запросу.

        Args:
            query: Текстовый запрос.
            artifact_type: Фильтр по типу артефакта (опционально).
            limit: Максимум результатов.

        Returns:
            Список найденных артефактов с оценкой релевантности.
        """
        await self._ensure_initialized()
        # TODO: векторный поиск через ChromaDB или sentence-transformers
        raise NotImplementedError("ArtifactKnowledgeBase.search — в разработке")

    async def get_by_id(self, artifact_id: str) -> Optional[ArtifactRecord]:
        """
        Получить артефакт по ID.

        Args:
            artifact_id: Уникальный идентификатор артефакта.

        Returns:
            Артефакт или None.
        """
        await self._ensure_initialized()
        # TODO: выборка из SQLite
        raise NotImplementedError("ArtifactKnowledgeBase.get_by_id — в разработке")
