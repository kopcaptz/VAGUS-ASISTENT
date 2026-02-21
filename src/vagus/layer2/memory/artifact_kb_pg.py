"""
ArtifactKnowledgeBasePG — PostgreSQL backend для базы знаний артефактов.
Использует asyncpg с пулом соединений. Реализует ArtifactKnowledgeBaseProtocol.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, List, Optional

from ...layer0.logging import get_logger
from .exceptions import ArtifactNotFoundError
from .schemas import ArtifactRecord, ArtifactSearchResult


def _pg_url(url: str) -> str:
    """Преобразует postgresql+asyncpg:// в postgresql:// для asyncpg."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


class ArtifactKnowledgeBasePG:
    """
    PostgreSQL backend для ArtifactKnowledgeBase.
    Требует выполненной миграции alembic (таблицы artifacts, artifact_relationships).
    """

    def __init__(
        self,
        postgres_url: str,
        *,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        self._postgres_url = _pg_url(postgres_url)
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None
        self.logger = get_logger("layer2.memory.artifact_kb_pg")

    async def _ensure_pool(self) -> None:
        """Ленивая инициализация пула соединений."""
        if self._pool is not None:
            return
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError("asyncpg is not installed") from exc
        self._pool = await asyncpg.create_pool(
            self._postgres_url,
            min_size=self._min_size,
            max_size=self._max_size,
        )
        self.logger.info("ArtifactKnowledgeBasePG pool created")

    async def close(self) -> None:
        """Закрыть пул соединений."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            self.logger.debug("ArtifactKnowledgeBasePG pool closed")

    async def _artifact_exists(self, artifact_id: str, tenant_id: str) -> bool:
        """Проверка существования артефакта по id и tenant."""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM artifacts WHERE artifact_id = $1 AND tenant_id = $2",
                artifact_id,
                tenant_id,
            )
        return row is not None

    async def get_artifact_id_by_plan_key(
        self,
        tenant_id: str,
        plan_id: str,
        key: str,
    ) -> Optional[str]:
        """Получить artifact_id по tenant_id, plan_id и key. None если не найден."""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT artifact_id FROM artifacts
                   WHERE tenant_id = $1 AND plan_id = $2 AND key = $3""",
                tenant_id,
                plan_id,
                key,
            )
        return row["artifact_id"] if row else None

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
        """Создать артефакт и сохранить в БД. Возвращает artifact_id."""
        await self._ensure_pool()
        artifact_id = str(uuid.uuid4())
        content_json = json.dumps({"content": content})
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO artifacts (
                    artifact_id, tenant_id, plan_id, key, content_json,
                    artifact_type, agent_type, session_id, source, ttl_seconds
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
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
            )
        return artifact_id

    async def link_artifacts(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        rel_type: str = "derived_from",
    ) -> None:
        """Связать два артефакта. Дубликаты игнорируются."""
        await self._ensure_pool()
        if not await self._artifact_exists(source_id, tenant_id):
            raise ArtifactNotFoundError(source_id)
        if not await self._artifact_exists(target_id, tenant_id):
            raise ArtifactNotFoundError(target_id)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO artifact_relationships
                   (tenant_id, source_id, target_id, rel_type, weight)
                   VALUES ($1, $2, $3, $4, 0.5)
                   ON CONFLICT (source_id, target_id, tenant_id) DO NOTHING""",
                tenant_id,
                source_id,
                target_id,
                rel_type,
            )

    async def _get_connection_weight(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
    ) -> Optional[float]:
        """Получить текущий вес связи."""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT weight FROM artifact_relationships
                   WHERE source_id = $1 AND target_id = $2 AND tenant_id = $3""",
                source_id,
                target_id,
                tenant_id,
            )
        return float(row["weight"]) if row is not None else None

    async def strengthen_connection(
        self,
        source_id: str,
        target_id: str,
        score: float,
        tenant_id: str,
    ) -> None:
        """Усилить связь между артефактами. Создаёт связь, если её нет."""
        await self._ensure_pool()
        weight = await self._get_connection_weight(source_id, target_id, tenant_id)
        delta = 0.1 * score
        if weight is None:
            if not await self._artifact_exists(source_id, tenant_id):
                raise ArtifactNotFoundError(source_id)
            if not await self._artifact_exists(target_id, tenant_id):
                raise ArtifactNotFoundError(target_id)
            new_weight = min(1.0, 0.5 + delta)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO artifact_relationships
                       (tenant_id, source_id, target_id, rel_type, weight)
                       VALUES ($1, $2, $3, 'derived_from', $4)""",
                    tenant_id,
                    source_id,
                    target_id,
                    new_weight,
                )
        else:
            new_weight = min(1.0, weight + delta)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """UPDATE artifact_relationships
                       SET weight = $1
                       WHERE source_id = $2 AND target_id = $3 AND tenant_id = $4""",
                    new_weight,
                    source_id,
                    target_id,
                    tenant_id,
                )

    async def weaken_connection(
        self,
        artifact_id: str,
        penalty: float,
        tenant_id: str,
    ) -> None:
        """Ослабить все связи, где artifact_id — source или target."""
        await self._ensure_pool()
        delta = 0.1 * penalty
        async with self._pool.acquire() as conn:
            await conn.execute(
                """UPDATE artifact_relationships
                   SET weight = GREATEST(0.0, weight - $1)
                   WHERE (source_id = $2 OR target_id = $2) AND tenant_id = $3""",
                delta,
                artifact_id,
                tenant_id,
            )

    async def strengthen_connections_batch(
        self,
        updates: List[dict],
        tenant_id: str,
    ) -> None:
        """
        Пакетное усиление связей.
        updates: [{"source_id": str, "target_id": str, "score": float}, ...]
        """
        if not updates:
            return
        await self._ensure_pool()

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
            params: List[Any] = [tenant_id]
            for i, u in enumerate(updates):
                or_parts.append(f"(source_id = ${i * 2 + 2} AND target_id = ${i * 2 + 3})")
                params.extend([u["source_id"], u["target_id"]])
            placeholders = " OR ".join(or_parts)
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(
                    f"""SELECT source_id, target_id, weight FROM artifact_relationships
                        WHERE tenant_id = $1 AND ({placeholders})""",
                    *params,
                )
            for row in rows:
                weight_map[(row["source_id"], row["target_id"])] = float(row["weight"])
        else:
            for u in updates:
                w = await self._get_connection_weight(
                    u["source_id"],
                    u["target_id"],
                    tenant_id,
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

        async with self._pool.acquire() as conn:
            if insert_params:
                await conn.executemany(
                    """INSERT INTO artifact_relationships
                       (tenant_id, source_id, target_id, rel_type, weight)
                       VALUES ($1, $2, $3, 'derived_from', $4)
                       ON CONFLICT (source_id, target_id, tenant_id) DO UPDATE
                       SET weight = EXCLUDED.weight""",
                    insert_params,
                )
            if update_params:
                await conn.executemany(
                    """UPDATE artifact_relationships
                       SET weight = $1
                       WHERE source_id = $2 AND target_id = $3 AND tenant_id = $4""",
                    update_params,
                )

    async def get_relationships_for_graph(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        """
        Получить связи для визуализации графа.
        Returns: [{"source_id": str, "target_id": str, "weight": float}, ...]
        """
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            if tenant_id is not None:
                rows = await conn.fetch(
                    """SELECT source_id, target_id, weight FROM artifact_relationships
                       WHERE tenant_id = $1 LIMIT $2""",
                    tenant_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """SELECT source_id, target_id, weight FROM artifact_relationships
                       LIMIT $1""",
                    limit,
                )
        return [
            {"source_id": r["source_id"], "target_id": r["target_id"], "weight": float(r["weight"])}
            for r in rows
        ]

    async def weaken_connections_batch(
        self,
        updates: List[dict],
        tenant_id: str,
    ) -> None:
        """
        Пакетное ослабление связей.
        updates: [{"artifact_id": str, "penalty": float}, ...]
        """
        if not updates:
            return
        await self._ensure_pool()

        params_list = [
            (0.1 * float(u.get("penalty", 1.0)), u.get("artifact_id"), u.get("artifact_id"), tenant_id)
            for u in updates
        ]

        async with self._pool.acquire() as conn:
            await conn.executemany(
                """UPDATE artifact_relationships
                   SET weight = GREATEST(0.0, weight - $1)
                   WHERE (source_id = $2 OR target_id = $2) AND tenant_id = $3""",
                params_list,
            )

    async def add(self, artifact: ArtifactRecord) -> None:
        """Добавить артефакт (заглушка)."""
        raise NotImplementedError("ArtifactKnowledgeBasePG.add — в разработке")

    async def search(
        self,
        query: str,
        artifact_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[ArtifactSearchResult]:
        """Семантический поиск (заглушка)."""
        raise NotImplementedError("ArtifactKnowledgeBasePG.search — в разработке")

    async def get_by_id(self, artifact_id: str) -> Optional[ArtifactRecord]:
        """Получить артефакт по ID (заглушка)."""
        raise NotImplementedError("ArtifactKnowledgeBasePG.get_by_id — в разработке")
