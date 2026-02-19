"""
Сервис кэширования ответов в памяти с поддержкой TTL.
Основано на реализации Manus AI.
"""

import hashlib
import time
from typing import Optional, Any, Dict, Tuple
from datetime import datetime
from ...layer0.logging import get_logger


class CacheService:
    """Сервис кэширования ответов в памяти с поддержкой TTL."""

    def __init__(self, ttl_seconds: int = 3600, max_size_mb: int = 100):
        """
        Инициализация кэш-сервиса.
        
        Args:
            ttl_seconds: Время жизни записей в кэше (по умолчанию 1 час)
            max_size_mb: Максимальный размер кэша в мегабайтах
        """
        self.ttl = ttl_seconds
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._cache: Dict[str, Tuple[Any, float, int]] = {}  # key -> (value, timestamp, size)
        self._total_size = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        
        self.logger = get_logger("cache")
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
        # Очищаем устаревшие записи перед добавлением
        self._cleanup_expired()
        
        key = self._generate_key(prompt, **kwargs)
        size = self._calculate_size(value)
        timestamp = time.monotonic()
        
        # Проверяем, не превысит ли добавление максимальный размер
        if self._total_size + size > self.max_size_bytes:
            self._evict_if_needed()
        
        # Если всё ещё не хватает места, не добавляем
        if self._total_size + size > self.max_size_bytes:
            self.logger.warning(f"Недостаточно места в кэше для ключа: {key[:16]}... (size: {size} bytes)")
            return
        
        # Удаляем старую запись если существует
        if key in self._cache:
            old_value, old_timestamp, old_size = self._cache[key]
            self._total_size -= old_size
        
        # Добавляем новую запись
        self._cache[key] = (value, timestamp, size)
        self._total_size += size
        
        self.logger.debug(f"Cache SET for key: {key[:16]}... (size: {size} bytes)")

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
            "hit_rate_percent": hit_rate,
            "ttl_seconds": self.ttl,
            "avg_entry_size_kb": (self._total_size / len(self._cache) / 1024) if self._cache else 0
        }

    def __str__(self) -> str:
        """Строковое представление."""
        stats = self.get_stats()
        return (
            f"CacheService(entries: {stats['total_entries']}, "
            f"size: {stats['total_size_mb']:.2f}MB/{stats['max_size_mb']:.2f}MB, "
            f"hit rate: {stats['hit_rate_percent']:.1f}%)"
        )