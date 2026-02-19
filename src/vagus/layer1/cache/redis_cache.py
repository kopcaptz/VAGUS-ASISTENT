"""
Secondary cache backend: Redis with SQLite fallback.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ...layer0.logging import get_logger


class RedisSecondaryCache:
    """
    Secondary cache for high-frequency entities.

    Приоритет чтения:
      1) Redis
      2) SQLite fallback
    """

    DEFAULT_TTLS = {
        "llm_response": 3600,       # 1 hour
        "provider_health": 120,     # 2 minutes
        "rate_limit_counter": 60,   # 1 minute
        "session_data": 3600,       # 1 hour
    }

    def __init__(
        self,
        *,
        redis_url: Optional[str] = None,
        sqlite_fallback_path: str = "cache_fallback.db",
        namespace_ttls: Optional[dict[str, int]] = None,
    ):
        self.logger = get_logger("cache.redis_secondary")
        self.redis_url = redis_url
        self.sqlite_fallback_path = Path(sqlite_fallback_path)
        self.sqlite_fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self.namespace_ttls = dict(self.DEFAULT_TTLS)
        if isinstance(namespace_ttls, dict):
            for key, value in namespace_ttls.items():
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    self.namespace_ttls[str(key)] = parsed

        self._redis = None
        self._redis_available = False
        self._redis_error: Optional[str] = None

        self._stats = {
            "redis_hits": 0,
            "redis_misses": 0,
            "redis_errors": 0,
            "sqlite_hits": 0,
            "sqlite_misses": 0,
            "sqlite_writes": 0,
        }

        self._init_sqlite_schema()
        self._try_init_redis()

    def _connect_sqlite(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_fallback_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite_schema(self) -> None:
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS secondary_cache (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(namespace, key)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_secondary_cache_expires_at
                ON secondary_cache(expires_at)
                """
            )

    def _try_init_redis(self) -> None:
        if not self.redis_url:
            self._redis = None
            self._redis_available = False
            self._redis_error = "redis_url_not_configured"
            return
        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]

            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            self._redis_available = True
            self._redis_error = None
            self.logger.info("Redis secondary cache enabled: %s", self.redis_url)
        except Exception as exc:
            self._redis = None
            self._redis_available = False
            self._redis_error = str(exc)
            self.logger.warning("Redis unavailable. Secondary cache fallback to SQLite: %s", exc)

    def _serialize(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def _deserialize(self, raw_value: str) -> Any:
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value

    def _redis_key(self, namespace: str, key: str) -> str:
        return f"vagus:cache:{namespace}:{key}"

    def _resolve_ttl(self, namespace: str, ttl_seconds: Optional[int]) -> int:
        if ttl_seconds is not None:
            try:
                value = int(ttl_seconds)
                return max(1, value)
            except (TypeError, ValueError):
                pass
        return int(self.namespace_ttls.get(namespace, 3600))

    def _sqlite_cleanup_expired(self) -> int:
        now = time.time()
        with self._connect_sqlite() as conn:
            cursor = conn.execute(
                "DELETE FROM secondary_cache WHERE expires_at <= ?",
                (now,),
            )
            return int(cursor.rowcount or 0)

    def _sqlite_get(self, namespace: str, key: str) -> Any:
        self._sqlite_cleanup_expired()
        now = time.time()
        with self._connect_sqlite() as conn:
            row = conn.execute(
                """
                SELECT value
                FROM secondary_cache
                WHERE namespace = ? AND key = ? AND expires_at > ?
                LIMIT 1
                """,
                (namespace, key, now),
            ).fetchone()
        if row is None:
            self._stats["sqlite_misses"] += 1
            return None
        self._stats["sqlite_hits"] += 1
        return self._deserialize(str(row["value"]))

    def _sqlite_set(self, namespace: str, key: str, value: Any, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        payload = self._serialize(value)
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                INSERT INTO secondary_cache(namespace, key, value, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key)
                DO UPDATE SET value=excluded.value, expires_at=excluded.expires_at, updated_at=excluded.updated_at
                """,
                (
                    namespace,
                    key,
                    payload,
                    expires_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        self._stats["sqlite_writes"] += 1

    def _sqlite_delete(self, namespace: str, key: str) -> None:
        with self._connect_sqlite() as conn:
            conn.execute(
                "DELETE FROM secondary_cache WHERE namespace = ? AND key = ?",
                (namespace, key),
            )

    def _sqlite_increment(self, namespace: str, key: str, amount: int, ttl_seconds: int) -> int:
        current_raw = self._sqlite_get(namespace, key)
        try:
            current_value = int(current_raw or 0)
        except (TypeError, ValueError):
            current_value = 0
        current_value += amount
        self._sqlite_set(namespace, key, current_value, ttl_seconds)
        return current_value

    async def _redis_get(self, namespace: str, key: str) -> Any:
        if not self._redis_available or self._redis is None:
            return None
        try:
            payload = await self._redis.get(self._redis_key(namespace, key))
            if payload is None:
                self._stats["redis_misses"] += 1
                return None
            self._stats["redis_hits"] += 1
            return self._deserialize(payload)
        except Exception as exc:
            self._stats["redis_errors"] += 1
            self._redis_available = False
            self._redis_error = str(exc)
            self.logger.warning("Redis read failed, fallback to SQLite: %s", exc)
            return None

    async def _redis_set(self, namespace: str, key: str, value: Any, ttl_seconds: int) -> bool:
        if not self._redis_available or self._redis is None:
            return False
        try:
            await self._redis.set(
                self._redis_key(namespace, key),
                self._serialize(value),
                ex=ttl_seconds,
            )
            return True
        except Exception as exc:
            self._stats["redis_errors"] += 1
            self._redis_available = False
            self._redis_error = str(exc)
            self.logger.warning("Redis write failed, fallback to SQLite: %s", exc)
            return False

    async def get(self, namespace: str, key: str) -> Any:
        """
        Reads value from secondary cache namespace.
        """
        redis_value = await self._redis_get(namespace, key)
        if redis_value is not None:
            return redis_value
        return self._sqlite_get(namespace, key)

    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        Writes value to Redis, with SQLite fallback.
        """
        ttl = self._resolve_ttl(namespace, ttl_seconds)
        if await self._redis_set(namespace, key, value, ttl):
            return
        self._sqlite_set(namespace, key, value, ttl)

    async def delete(self, namespace: str, key: str) -> None:
        if self._redis_available and self._redis is not None:
            try:
                await self._redis.delete(self._redis_key(namespace, key))
            except Exception:
                self._stats["redis_errors"] += 1
                self._redis_available = False
        self._sqlite_delete(namespace, key)

    async def increment(
        self,
        namespace: str,
        key: str,
        *,
        amount: int = 1,
        ttl_seconds: Optional[int] = None,
    ) -> int:
        """
        Counter helper for rate-limiting use-cases.
        """
        ttl = self._resolve_ttl(namespace, ttl_seconds)
        if self._redis_available and self._redis is not None:
            try:
                redis_key = self._redis_key(namespace, key)
                value = await self._redis.incrby(redis_key, int(amount))
                if int(value) == int(amount):
                    await self._redis.expire(redis_key, ttl)
                return int(value)
            except Exception as exc:
                self._stats["redis_errors"] += 1
                self._redis_available = False
                self._redis_error = str(exc)
                self.logger.warning("Redis increment failed, fallback to SQLite: %s", exc)
        return self._sqlite_increment(namespace, key, int(amount), ttl)

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "redis_enabled": self._redis_available,
            "redis_url": self.redis_url,
            "redis_error": self._redis_error,
            "sqlite_fallback_path": str(self.sqlite_fallback_path),
            "namespace_ttls": dict(self.namespace_ttls),
        }

