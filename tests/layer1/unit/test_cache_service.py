"""Unit-тесты CacheService."""
import pytest
from vagus.layer1.cache import CacheService


@pytest.mark.asyncio
async def test_cache_set_get():
    cache = CacheService(ttl_seconds=60, max_size_mb=1)
    await cache.set("hello", "world")
    val = await cache.get("hello")
    assert val == "world"


@pytest.mark.asyncio
async def test_cache_miss():
    cache = CacheService(ttl_seconds=60, max_size_mb=1)
    val = await cache.get("nonexistent")
    assert val is None


@pytest.mark.asyncio
async def test_cache_stats():
    cache = CacheService(ttl_seconds=60, max_size_mb=1)
    await cache.set("a", "1")
    await cache.get("a")
    await cache.get("b")
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
