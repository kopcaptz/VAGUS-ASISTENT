"""
SharedBlackboard — общее хранилище промежуточных артефактов.
Redis Hash backend с in-memory fallback.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ...layer0.logging import get_logger

BLACKBOARD_KEY_PREFIX = "vagus:blackboard"
TTL_SECONDS = 86400  # 24 hours


def create_blackboard_from_config(layer2_config: Optional[Dict[str, Any]]) -> "SharedBlackboard":
    """Создаёт SharedBlackboard из конфигурации layer2."""
    bb_cfg = (layer2_config or {}).get("blackboard") or {}
    redis_url = bb_cfg.get("redis_url") if bb_cfg.get("enabled", True) else None
    return SharedBlackboard(redis_url=redis_url)


class SharedBlackboard:
    """
    Общее хранилище промежуточных артефактов для задач.
    Redis Hash при наличии redis_url, иначе in-memory dict.
    """

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self.logger = get_logger("layer2.blackboard")
        self._redis_url = redis_url
        self._redis = None
        self._store: Dict[str, Dict[str, Any]] = {}

        if redis_url:
            try:
                import redis.asyncio as redis  # type: ignore[import-untyped]
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self.logger.info("Blackboard using Redis backend: %s", redis_url[:50])
            except Exception as exc:  # pragma: no cover - optional dependency
                self.logger.warning("Redis unavailable, fallback to in-memory: %s", exc)
                self._redis = None
        else:
            self.logger.debug("Blackboard using in-memory backend")

    def _redis_key(self, task_id: str) -> str:
        return f"{BLACKBOARD_KEY_PREFIX}:{task_id}"

    def _serialize(self, value: Any) -> str:
        """Сериализует value в JSON (если не строка)."""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def _deserialize(self, raw: str) -> Any:
        """Десериализует JSON если возможно."""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    async def write(self, task_id: str, key: str, value: Any) -> None:
        """Записывает значение по ключу для задачи. Сериализует value в JSON (если не строка)."""
        serialized = self._serialize(value)
        if self._redis:
            rkey = self._redis_key(task_id)
            await self._redis.hset(rkey, key, serialized)
            await self._redis.expire(rkey, TTL_SECONDS)
            self.logger.debug("Written blackboard[%s][%s]", task_id, key)
        else:
            if task_id not in self._store:
                self._store[task_id] = {}
            self._store[task_id][key] = value
            self.logger.debug("Written blackboard[%s][%s] (memory)", task_id, key)

    async def read(self, task_id: str, key: str) -> Any:
        """Читает значение по ключу. Десериализует JSON при необходимости. None если ключ отсутствует."""
        if self._redis:
            rkey = self._redis_key(task_id)
            raw = await self._redis.hget(rkey, key)
            if raw is None:
                return None
            return self._deserialize(raw)
        else:
            task_data = self._store.get(task_id)
            if task_data is None:
                return None
            return task_data.get(key)

    async def read_all(self, task_id: str) -> Dict[str, Any]:
        """Возвращает все артефакты для задачи."""
        if self._redis:
            rkey = self._redis_key(task_id)
            raw_map = await self._redis.hgetall(rkey)
            if not raw_map:
                return {}
            return {k: self._deserialize(v) for k, v in raw_map.items()}
        else:
            return dict(self._store.get(task_id, {}))

    async def clear(self, task_id: str) -> None:
        """Удаляет все артефакты задачи."""
        if self._redis:
            rkey = self._redis_key(task_id)
            await self._redis.delete(rkey)
            self.logger.debug("Cleared blackboard[%s]", task_id)
        else:
            self._store.pop(task_id, None)
            self.logger.debug("Cleared blackboard[%s] (memory)", task_id)
