"""
Сервис кэширования ответов в памяти с поддержкой TTL.
Основано на реализации Manus AI.
"""

import hashlib
import time
from typing import Optional, Any, Dict, Tuple
from ...layer0.logging import get_logger
from .redis_cache import RedisSecondaryCache


class CacheService:
    """Сервис кэширования ответов в памяти с поддержкой TTL."""

    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_size_mb: int = 100,
        *,
        enable_secondary_cache: bool = False,
        secondary_redis_url: Optional[str] = None,
        secondary_sqlite_path: str = "cache_fallback.db",
        secondary_namespace_ttls: Optional[Dict[str, int]] = None,
    ):
        """
        Инициализация кэш-сервиса.
        
        Args:
            ttl_seconds: Время жизни записей в кэше (по умолчанию 1 час)
            max_size_mb: Максимальный размер кэша в мегабайтах
            enable_secondary_cache: Включить secondary cache (Redis/SQLite)
            secondary_redis_url: Redis URL для secondary cache
            secondary_sqlite_path: SQLite fallback путь для secondary cache
            secondary_namespace_ttls: TTL по namespace для secondary cache
        """
        self.ttl = ttl_seconds
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._cache: Dict[str, Tuple[Any, float, int]] = {}  # key -> (value, timestamp, size)
        self._total_size = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._secondary_hits = 0
        self._secondary_misses = 0
        
        self.logger = get_logger("cache")
        self.secondary_cache: Optional[RedisSecondaryCache] = None
        if enable_secondary_cache or secondary_redis_url:
            self.secondary_cache = RedisSecondaryCache(
                redis_url=secondary_redis_url,
                sqlite_fallback_path=secondary_sqlite_path,
                namespace_ttls=secondary_namespace_ttls,
            )
            self.logger.info(
                "Secondary cache enabled (redis=%s, sqlite_fallback=%s)",
                secondary_redis_url,
                secondary_sqlite_path,
            )
        self.logger.info(
            f"CacheService инициализирован (TTL: {ttl_seconds}с, "
            f"max size: {max_size_mb}MB)"
        )

    def _generate_key(self, prompt: str, **kwargs) -> str:
        """
        Генерирует детерминированный ключ кэша.
        
        Args:
            prompt: Текст промпта
            **kwargs: Дополнительные параметры
            
        Returns:
            SHA-256 хэш ключа
        """
        # Создаём строку для хэширования
        key_parts = [prompt]
        
        # Добавляем отсортированные параметры
        if kwargs:
            sorted_items = sorted(kwargs.items())
            key_parts.append(str(sorted_items))
        
        key_string = "|".join(key_parts)
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _calculate_size(self, value: Any) -> int:
        """
        Оценивает размер значения в байтах.
        
        Args:
            value: Значение для оценки
            
        Returns:
            Примерный размер в байтах
        """
        if isinstance(value, str):
            return len(value.encode('utf-8'))
        elif isinstance(value, (dict, list)):
            return len(str(value).encode('utf-8'))
        else:
            return len(str(value).encode('utf-8'))

    def _cleanup_expired(self) -> None:
        """Очищает устаревшие записи из кэша."""
        current_time = time.monotonic()
        expired_keys = []
        
        for key, (value, timestamp, size) in list(self._cache.items()):
            if current_time - timestamp > self.ttl:
                expired_keys.append(key)
                self._total_size -= size
                self._evictions += 1
        
        for key in expired_keys:
            del self._cache[key]
        
        if expired_keys:
            self.logger.debug(f"Очищено {len(expired_keys)} устаревших записей")

    def _evict_if_needed(self) -> None:
        """Вытесняет старые записи если превышен максимальный размер."""
        if self._total_size <= self.max_size_bytes:
            return
        
        # Сортируем записи по времени добавления (старые сначала)
        sorted_entries = sorted(
            self._cache.items(),
            key=lambda x: x[1][1]  # по timestamp
        )
        
        evicted_count = 0
        while self._total_size > self.max_size_bytes and sorted_entries:
            key, (value, timestamp, size) = sorted_entries.pop(0)
            del self._cache[key]
            self._total_size -= size
            self._evictions += 1
            evicted_count += 1
        
        if evicted_count > 0:
            self.logger.info(f"Вытеснено {evicted_count} записей из-за превышения размера")

    def _set_memory_entry(self, key: str, value: Any) -> bool:
        """
        Записывает значение в in-memory cache по готовому ключу.

        Returns:
            True если запись добавлена.
        """
        self._cleanup_expired()
        size = self._calculate_size(value)
        timestamp = time.monotonic()

        if self._total_size + size > self.max_size_bytes:
            self._evict_if_needed()

        if self._total_size + size > self.max_size_bytes:
            self.logger.warning(
                "Недостаточно места в кэше для ключа: %s... (size: %s bytes)",
                key[:16],
                size,
            )
            return False

        if key in self._cache:
            _, _, old_size = self._cache[key]
            self._total_size -= old_size

        self._cache[key] = (value, timestamp, size)
        self._total_size += size
        return True

    async def get(self, prompt: str, **kwargs) -> Optional[Any]:
        """
        Возвращает значение из кэша.
        
        Args:
            prompt: Текст промпта
            **kwargs: Дополнительные параметры
            
        Returns:
            Значение из кэша или None
        """
        # Очищаем устаревшие записи перед поиском
        self._cleanup_expired()
        
        key = self._generate_key(prompt, **kwargs)
        entry = self._cache.get(key)
        
        if entry is None:
            if self.secondary_cache is not None:
                secondary_value = await self.secondary_cache.get("llm_response", key)
                if secondary_value is not None:
                    self._secondary_hits += 1
                    self._hits += 1
                    self._set_memory_entry(key, secondary_value)
                    self.logger.debug("Secondary cache HIT for key: %s...", key[:16])
                    return secondary_value
                self._secondary_misses += 1
            self._misses += 1
            self.logger.debug(f"Cache MISS for key: {key[:16]}...")
            return None
        
        value, timestamp, size = entry
        current_time = time.monotonic()
        
        # Проверяем TTL
        if current_time - timestamp > self.ttl:
            del self._cache[key]
            self._total_size -= size
            self._evictions += 1
            self._misses += 1
            self.logger.debug(f"Cache EXPIRED for key: {key[:16]}...")
            return None
        
        self._hits += 1
        self.logger.debug(f"Cache HIT for key: {key[:16]}...")
        return value

    async def set(self, prompt: str, value: Any, **kwargs) -> None:
        """
        Сохраняет значение в кэш.
        
        Args:
            prompt: Текст промпта
            value: Значение для кэширования
            **kwargs: Дополнительные параметры
        """
        key = self._generate_key(prompt, **kwargs)
        if self._set_memory_entry(key, value):
            self.logger.debug(f"Cache SET for key: {key[:16]}...")
        if self.secondary_cache is not None:
            await self.secondary_cache.set(
                "llm_response",
                key,
                value,
                ttl_seconds=self.ttl,
            )

    async def set_provider_health(
        self,
        provider_id: str,
        payload: Dict[str, Any],
        *,
        ttl_seconds: int = 120,
    ) -> None:
        """Сохраняет health-status провайдера во secondary cache."""
        if self.secondary_cache is None:
            return
        await self.secondary_cache.set(
            "provider_health",
            provider_id,
            payload,
            ttl_seconds=ttl_seconds,
        )

    async def get_provider_health(self, provider_id: str) -> Optional[Dict[str, Any]]:
        """Получает health-status провайдера из secondary cache."""
        if self.secondary_cache is None:
            return None
        value = await self.secondary_cache.get("provider_health", provider_id)
        return value if isinstance(value, dict) else None

    async def increment_rate_limit_counter(
        self,
        counter_key: str,
        *,
        amount: int = 1,
        ttl_seconds: int = 60,
    ) -> int:
        """Инкрементирует secondary cache счётчик rate limit."""
        if self.secondary_cache is None:
            return int(amount)
        return await self.secondary_cache.increment(
            "rate_limit_counter",
            counter_key,
            amount=amount,
            ttl_seconds=ttl_seconds,
        )

    async def set_session_data(
        self,
        session_id: str,
        payload: Dict[str, Any],
        *,
        ttl_seconds: int = 3600,
    ) -> None:
        """Сохраняет session payload в secondary cache."""
        if self.secondary_cache is None:
            return
        await self.secondary_cache.set(
            "session_data",
            session_id,
            payload,
            ttl_seconds=ttl_seconds,
        )

    async def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Возвращает session payload из secondary cache."""
        if self.secondary_cache is None:
            return None
        value = await self.secondary_cache.get("session_data", session_id)
        return value if isinstance(value, dict) else None

    async def close(self) -> None:
        """Закрывает внешние backend-ресурсы кэша."""
        if self.secondary_cache is not None:
            await self.secondary_cache.close()

    def clear(self) -> None:
        """Очищает весь кэш."""
        count = len(self._cache)
        total_size = self._total_size
        
        self._cache.clear()
        self._total_size = 0
        
        self.logger.info(f"Кэш очищен ({count} записей, {total_size / 1024 / 1024:.2f} MB)")

    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику кэша.
        
        Returns:
            Словарь со статистикой
        """
        self._cleanup_expired()
        
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "total_entries": len(self._cache),
            "total_size_mb": self._total_size / 1024 / 1024,
            "max_size_mb": self.max_size_bytes / 1024 / 1024,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "secondary_hits": self._secondary_hits,
            "secondary_misses": self._secondary_misses,
            "hit_rate_percent": hit_rate,
            "ttl_seconds": self.ttl,
            "avg_entry_size_kb": (self._total_size / len(self._cache) / 1024) if self._cache else 0,
            "secondary_cache": (
                self.secondary_cache.get_stats() if self.secondary_cache is not None else None
            ),
        }

    def __str__(self) -> str:
        """Строковое представление."""
        stats = self.get_stats()
        return (
            f"CacheService(entries: {stats['total_entries']}, "
            f"size: {stats['total_size_mb']:.2f}MB/{stats['max_size_mb']:.2f}MB, "
            f"hit rate: {stats['hit_rate_percent']:.1f}%)"
        )