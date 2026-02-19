"""
SQLite хранилище метрик для мониторинга запросов LLM.
"""

import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from ...layer0.logging import get_logger


class MetricsStorage:
    """SQLite хранилище метрик запросов."""

    def __init__(
        self,
        db_path: str = "metrics.db",
        *,
        vacuum_interval_seconds: int = 3600,
    ):
        """
        Инициализация хранилища.

        Args:
            db_path: Путь к файлу SQLite базы данных
            vacuum_interval_seconds: Минимальный интервал между VACUUM
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("monitoring.metrics_storage")
        self.vacuum_interval_seconds = max(60, int(vacuum_interval_seconds))
        self._last_vacuum_ts = 0.0
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Создаёт таблицы если не существуют."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS request_metrics (
                    trace_id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    ttft_ms REAL,
                    e2e_ms REAL,
                    cost_usd REAL,
                    success INTEGER NOT NULL,
                    error_type TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_provider ON request_metrics(provider)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON request_metrics(timestamp)
            """)
            self._ensure_compat_indexes(conn)
        self.logger.debug(f"MetricsStorage инициализирован: {self.db_path}")

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None

    def _ensure_compat_indexes(self, conn: sqlite3.Connection) -> None:
        """
        Создаёт индексы для частых запросов (включая legacy naming).
        """
        # Основная таблица в проекте — request_metrics.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_provider ON request_metrics(provider)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON request_metrics(timestamp)"
        )

        # Если в той же БД присутствует таблица audit_log, добавляем индекс timestamp.
        if self._table_exists(conn, "audit_log"):
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp)"
            )

    def insert(
        self,
        trace_id: str,
        provider: str,
        model: str,
        ttft_ms: Optional[float] = None,
        e2e_ms: Optional[float] = None,
        cost_usd: float = 0.0,
        success: bool = True,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Вставляет запись метрики.

        Args:
            trace_id: Уникальный ID запроса
            provider: Имя провайдера
            model: Модель
            ttft_ms: Time to first token в мс
            e2e_ms: End-to-end latency в мс
            cost_usd: Стоимость в USD
            success: Успешность запроса
            error_type: Тип ошибки (если не успешно)
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO request_metrics
                (trace_id, provider, model, ttft_ms, e2e_ms, cost_usd, success, error_type, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trace_id,
                    provider,
                    model,
                    ttft_ms,
                    e2e_ms,
                    cost_usd,
                    1 if success else 0,
                    error_type,
                    datetime.utcnow().isoformat(),
                ),
            )
        self.logger.debug(f"Metric recorded: trace_id={trace_id[:8]}..., provider={provider}")

    def get_stats(
        self,
        provider: Optional[str] = None,
        retention_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Возвращает агрегированную статистику.

        Args:
            provider: Фильтр по провайдеру (опционально)
            retention_days: Учитывать только записи за последние N дней

        Returns:
            Словарь со статистикой
        """
        conditions = []
        params: List[Any] = []
        if retention_days:
            cutoff_dt = datetime.utcnow() - timedelta(days=retention_days)
            conditions.append("timestamp >= ?")
            params.append(cutoff_dt.isoformat())
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""

        with self._connect() as conn:
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM request_metrics{where_sql}",
                params,
            )
            total = cursor.fetchone()[0] or 0

            cursor = conn.execute(
                f"SELECT SUM(success) FROM request_metrics{where_sql}",
                params,
            )
            success_count = cursor.fetchone()[0] or 0

            cursor = conn.execute(
                f"SELECT AVG(e2e_ms), AVG(ttft_ms), SUM(cost_usd) FROM request_metrics{where_sql}",
                params,
            )
            row = cursor.fetchone()
            avg_e2e = row[0] if row and row[0] is not None else 0
            avg_ttft = row[1] if row and row[1] is not None else 0
            total_cost = row[2] if row and row[2] is not None else 0

        return {
            "total_requests": total,
            "success_count": success_count,
            "failure_count": total - success_count,
            "success_rate": (success_count / total * 100) if total > 0 else 0,
            "avg_e2e_ms": round(float(avg_e2e), 2),
            "avg_ttft_ms": round(float(avg_ttft), 2),
            "total_cost_usd": round(float(total_cost), 6),
        }

    def get_recent_requests(
        self,
        *,
        limit: int = 100,
        provider: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Возвращает последние записи с ORDER BY + LIMIT для быстрых UI/API выборок.
        """
        safe_limit = max(1, int(limit))
        conditions = []
        params: List[Any] = []
        if provider:
            conditions.append("provider = ?")
            params.append(provider)
        where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(safe_limit)

        query = f"""
            SELECT
                trace_id, provider, model, ttft_ms, e2e_ms,
                cost_usd, success, error_type, timestamp
            FROM request_metrics
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_top_providers(
        self,
        *,
        limit: int = 10,
        retention_days: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Возвращает топ провайдеров по числу запросов.
        """
        safe_limit = max(1, int(limit))
        conditions = []
        params: List[Any] = []
        if retention_days:
            cutoff_dt = datetime.utcnow() - timedelta(days=retention_days)
            conditions.append("timestamp >= ?")
            params.append(cutoff_dt.isoformat())
        where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
        params.append(safe_limit)

        query = f"""
            SELECT
                provider,
                COUNT(*) AS request_count,
                AVG(e2e_ms) AS avg_e2e_ms,
                SUM(cost_usd) AS total_cost_usd
            FROM request_metrics
            {where_sql}
            GROUP BY provider
            ORDER BY request_count DESC
            LIMIT ?
        """
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def vacuum(self, *, force: bool = False) -> bool:
        """
        Периодическая очистка SQLite (VACUUM).

        Returns:
            True если VACUUM выполнен.
        """
        now_ts = datetime.utcnow().timestamp()
        if not force and (now_ts - self._last_vacuum_ts) < self.vacuum_interval_seconds:
            return False
        with self._connect() as conn:
            conn.execute("VACUUM")
        self._last_vacuum_ts = now_ts
        self.logger.info("SQLite VACUUM executed for metrics storage")
        return True

    def cleanup_old(self, retention_days: int = 30) -> int:
        """
        Удаляет записи старше retention_days.

        Args:
            retention_days: Хранить записи за последние N дней

        Returns:
            Количество удалённых записей
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM request_metrics WHERE timestamp < ?",
                (cutoff.isoformat(),),
            )
            deleted = cursor.rowcount
        if deleted > 0:
            self.vacuum()
        if deleted > 0:
            self.logger.info(f"Cleaned up {deleted} old metrics (retention: {retention_days} days)")
        return deleted

    @staticmethod
    def generate_trace_id() -> str:
        """Генерирует уникальный trace_id."""
        return str(uuid.uuid4())
