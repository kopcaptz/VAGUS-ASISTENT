"""
EpisodicMemory — хранение истории выполнения задач (краткосрочная память).
"""

import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiosqlite


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS episodic_steps (
    step_id       TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    task_id       TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    agent_type    TEXT NOT NULL,
    action        TEXT NOT NULL,
    result_json   TEXT NOT NULL,
    metadata_json TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_task_id ON episodic_steps(task_id);
"""
CREATE_INDEX_TENANT_TASK = """
CREATE INDEX IF NOT EXISTS idx_episodic_tenant_task ON episodic_steps(tenant_id, task_id);
"""


class EpisodicMemory:
    """
    SQLite-backed хранилище истории выполнения задач.
    По умолчанию использует in-memory SQLite для обратной совместимости в тестах.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._db_path = db_path
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._conn: aiosqlite.Connection = self._run(self._open_connection())

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run(self, coro: Any) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    async def _open_connection(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self._db_path)
        await conn.execute(CREATE_TABLE_SQL)
        await conn.execute(CREATE_INDEX_SQL)
        await conn.execute(CREATE_INDEX_TENANT_TASK)
        await conn.commit()
        return conn

    async def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self._conn.execute(sql, params)
        await self._conn.commit()

    async def _executemany(self, sql: str, params: List[tuple[Any, ...]]) -> None:
        await self._conn.executemany(sql, params)
        await self._conn.commit()

    async def _fetchall(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> List[tuple[Any, ...]]:
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchall()

    async def _fetchone(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> Optional[tuple[Any, ...]]:
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    @staticmethod
    def _make_step(
        step_id: str,
        timestamp: str,
        agent_type: str,
        action: str,
        result_json: str,
        metadata_json: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "step_id": step_id,
            "timestamp": timestamp,
            "agent_type": agent_type,
            "action": action,
            "result": json.loads(result_json),
            "metadata": json.loads(metadata_json) if metadata_json else {},
        }

    async def _add_step_impl(
        self,
        tenant_id: str,
        task_id: str,
        agent_type: str,
        action: str,
        result: Any,
        metadata: Optional[Dict[str, Any]],
        step_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> str:
        """Async реализация добавления шага."""
        step_id = step_id or uuid.uuid4().hex
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        result_json = json.dumps(result, ensure_ascii=False)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
        await self._execute(
            """
            INSERT INTO episodic_steps
            (step_id, tenant_id, task_id, timestamp, agent_type, action, result_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step_id,
                tenant_id,
                task_id,
                timestamp,
                agent_type,
                action,
                result_json,
                metadata_json,
            ),
        )
        return step_id

    async def add_step_async(
        self,
        tenant_id: str,
        task_id: str,
        agent_type: str,
        action: str,
        result: dict,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Добавляет шаг в историю задачи (async API).

        Args:
            tenant_id: Идентификатор tenant.
            task_id: Идентификатор задачи.
            agent_type: Тип агента.
            action: Действие.
            result: Результат выполнения (dict).
            metadata: Дополнительные данные.

        Returns:
            step_id — UUID4 идентификатор шага.
        """
        future = asyncio.run_coroutine_threadsafe(
            self._add_step_impl(
                tenant_id, task_id, agent_type, action, result, metadata
            ),
            self._loop,
        )
        return await asyncio.wrap_future(future)

    def add_step(
        self,
        task_id: str,
        agent_type: Any,
        action: Optional[str] = None,
        result: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Добавляет шаг в историю задачи.

        Args:
            task_id: Идентификатор задачи
            agent_type: Тип агента (researcher|coder|analyst)
            action: Действие (search_web|execute_code|analyze_data)
            result: Результат выполнения
            metadata: Дополнительные данные

        Returns:
            step_id — уникальный идентификатор шага
        """
        if isinstance(agent_type, dict) and action is None:
            step_dict = agent_type
            step_id = str(step_dict.get("step_id") or uuid.uuid4().hex)
            timestamp = str(
                step_dict.get("timestamp")
                or datetime.now(timezone.utc).isoformat()
            )
            agent_type_value = str(step_dict.get("agent_type") or "unknown")
            action_value = str(step_dict.get("action") or "unknown")
            result_value = step_dict.get("result")
            metadata_value = step_dict.get("metadata") or {}
            return self._run(
                self._add_step_impl(
                    "default",
                    task_id,
                    agent_type_value,
                    action_value,
                    result_value,
                    metadata_value,
                    step_id=step_id,
                    timestamp=timestamp,
                )
            )
        if action is None:
            raise ValueError(
                "action is required when using positional add_step signature"
            )
        agent_type_value = str(agent_type)
        action_value = action
        result_value = result
        metadata_value = metadata or {}
        return self._run(
            self._add_step_impl(
                "default",
                task_id,
                agent_type_value,
                action_value,
                result_value,
                metadata_value,
            )
        )

    def get_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Возвращает список всех шагов задачи в порядке добавления.
        Использует tenant_id='default' для обратной совместимости.

        Returns:
            Список шагов или пустой список, если задача не найдена
        """
        rows = self._run(
            self._fetchall(
                """
                SELECT step_id, timestamp, agent_type, action, result_json, metadata_json
                FROM episodic_steps
                WHERE tenant_id = ? AND task_id = ?
                ORDER BY timestamp ASC, rowid ASC
                """,
                ("default", task_id),
            )
        )
        return [self._make_step(*row) for row in rows]

    async def get_recent_history(
        self, tenant_id: str, task_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Возвращает последние limit шагов для tenant_id и task_id.
        Сортировка по created_at DESC.
        """

        async def _fetch() -> List[Dict[str, Any]]:
            rows = await self._fetchall(
                """
                SELECT step_id, timestamp, agent_type, action, result_json, metadata_json
                FROM episodic_steps
                WHERE tenant_id = ? AND task_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT ?
                """,
                (tenant_id, task_id, limit),
            )
            return [self._make_step(*row) for row in rows]

        future = asyncio.run_coroutine_threadsafe(_fetch(), self._loop)
        return await asyncio.wrap_future(future)

    def get_last_step(self, task_id: str, tenant_id: str = "default") -> Optional[Dict[str, Any]]:
        """
        Возвращает последний шаг задачи или None.

        Args:
            task_id: Идентификатор задачи.
            tenant_id: Идентификатор tenant (по умолчанию "default").

        Returns:
            Последний шаг или None
        """
        row = self._run(
            self._fetchone(
                """
                SELECT step_id, timestamp, agent_type, action, result_json, metadata_json
                FROM episodic_steps
                WHERE tenant_id = ? AND task_id = ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT 1
                """,
                (tenant_id, task_id),
            )
        )
        return self._make_step(*row) if row else None

    def clear_task_history(self, task_id: str, tenant_id: str = "default") -> None:
        """Удаляет всю историю шагов для задачи."""
        self._run(
            self._execute(
                "DELETE FROM episodic_steps WHERE tenant_id = ? AND task_id = ?",
                (tenant_id, task_id),
            )
        )

    def add_steps_batch(
        self,
        task_or_steps: Any,
        steps: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Batch: добавляет несколько шагов за один вызов.
        Поддерживает два формата:
        1) add_steps_batch([(task_id, agent_type, action, result, metadata), ...])
        2) add_steps_batch(task_id, [step_dict, ...])
        """
        step_ids = []
        payload = []
        tenant_id = "default"

        if isinstance(task_or_steps, str):
            task_id = task_or_steps
            for step in steps or []:
                step_id = str(step.get("step_id") or uuid.uuid4().hex)
                timestamp = str(step.get("timestamp") or datetime.now(timezone.utc).isoformat())
                step_ids.append(step_id)
                payload.append(
                    (
                        step_id,
                        tenant_id,
                        task_id,
                        timestamp,
                        str(step.get("agent_type") or "unknown"),
                        str(step.get("action") or "unknown"),
                        json.dumps(step.get("result"), ensure_ascii=False),
                        json.dumps(step.get("metadata") or {}, ensure_ascii=False),
                    )
                )
        else:
            for task_id, agent_type, action, result, metadata in task_or_steps:
                step_id = uuid.uuid4().hex
                timestamp = datetime.now(timezone.utc).isoformat()
                step_ids.append(step_id)
                payload.append(
                    (
                        step_id,
                        tenant_id,
                        task_id,
                        timestamp,
                        agent_type,
                        action,
                        json.dumps(result, ensure_ascii=False),
                        json.dumps(metadata or {}, ensure_ascii=False),
                    )
                )

        if not payload:
            return step_ids

        self._run(
            self._executemany(
                """
                INSERT INTO episodic_steps
                (step_id, tenant_id, task_id, timestamp, agent_type, action, result_json, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
        )
        return step_ids

    def get_all_tasks(self) -> List[str]:
        """Возвращает список всех task_id с непустой историей (tenant_id='default')."""
        rows = self._run(
            self._fetchall(
                """
                SELECT DISTINCT task_id
                FROM episodic_steps
                WHERE tenant_id = ?
                ORDER BY task_id ASC
                """,
                ("default",),
            )
        )
        return [row[0] for row in rows]

    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        """
        Возвращает сводку по задаче.

        Returns:
            Dict с step_count, last_step, first_timestamp, last_timestamp
        """
        count_row = self._run(
            self._fetchone(
                "SELECT COUNT(*) FROM episodic_steps WHERE tenant_id = ? AND task_id = ?",
                ("default", task_id),
            )
        )
        step_count = int(count_row[0]) if count_row else 0

        if step_count == 0:
            return {
                "task_id": task_id,
                "step_count": 0,
                "last_step": None,
                "first_timestamp": None,
                "last_timestamp": None,
            }

        first_row = self._run(
            self._fetchone(
                """
                SELECT step_id, timestamp, agent_type, action, result_json, metadata_json
                FROM episodic_steps
                WHERE tenant_id = ? AND task_id = ?
                ORDER BY timestamp ASC, rowid ASC
                LIMIT 1
                """,
                ("default", task_id),
            )
        )
        last_row = self._run(
            self._fetchone(
                """
                SELECT step_id, timestamp, agent_type, action, result_json, metadata_json
                FROM episodic_steps
                WHERE tenant_id = ? AND task_id = ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT 1
                """,
                ("default", task_id),
            )
        )
        first = self._make_step(*first_row) if first_row else None
        last = self._make_step(*last_row) if last_row else None

        return {
            "task_id": task_id,
            "step_count": step_count,
            "last_step": last,
            "first_timestamp": first.get("timestamp") if first else None,
            "last_timestamp": last.get("timestamp") if last else None,
        }

    def close(self) -> None:
        """Закрывает соединение и фоновый event loop."""
        if not self._loop.is_running():
            return
        self._run(self._conn.close())
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=1)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


__all__ = ["EpisodicMemory"]
