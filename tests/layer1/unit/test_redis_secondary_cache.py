"""Tests for Redis secondary cache and SQLite fallback."""

import pytest

from vagus.layer1.cache import CacheService
from vagus.layer1.cache.redis_cache import RedisSecondaryCache


@pytest.mark.asyncio
async def test_secondary_cache_sqlite_fallback_set_get(tmp_path):
    cache = RedisSecondaryCache(
        redis_url=None,
        sqlite_fallback_path=str(tmp_path / "fallback.db"),
    )
    await cache.set("llm_response", "k1", {"value": 1}, ttl_seconds=3600)
    value = await cache.get("llm_response", "k1")
    assert value == {"value": 1}
    stats = cache.get_stats()
    assert stats["sqlite_writes"] >= 1


@pytest.mark.asyncio
async def test_secondary_cache_increment_and_session_namespace(tmp_path):
    cache = RedisSecondaryCache(
        redis_url=None,
        sqlite_fallback_path=str(tmp_path / "fallback.db"),
    )
    count1 = await cache.increment("rate_limit_counter", "user:1", amount=1, ttl_seconds=60)
    count2 = await cache.increment("rate_limit_counter", "user:1", amount=2, ttl_seconds=60)
    assert count1 == 1
    assert count2 == 3

    await cache.set("session_data", "session-1", {"user_id": "u1"}, ttl_seconds=3600)
    assert await cache.get("session_data", "session-1") == {"user_id": "u1"}


@pytest.mark.asyncio
async def test_cache_service_uses_secondary_cache_after_memory_miss(tmp_path):
    sqlite_path = str(tmp_path / "fallback.db")
    cache_writer = CacheService(
        ttl_seconds=3600,
        max_size_mb=1,
        enable_secondary_cache=True,
        secondary_sqlite_path=sqlite_path,
    )
    await cache_writer.set("prompt-1", "answer-1")

    cache_reader = CacheService(
        ttl_seconds=3600,
        max_size_mb=1,
        enable_secondary_cache=True,
        secondary_sqlite_path=sqlite_path,
    )
    value = await cache_reader.get("prompt-1")
    assert value == "answer-1"
    stats = cache_reader.get_stats()
    assert stats["secondary_hits"] >= 1
