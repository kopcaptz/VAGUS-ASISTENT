"""
SemanticMemory — векторное хранилище для долгосрочной памяти.
Поиск похожих задач по эмбеддингам промптов.
"""

import hashlib
import math
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

if TYPE_CHECKING:
    from .episodic import EpisodicMemory

from ...layer0.logging import get_logger


class EmbedderProtocol(Protocol):
    """Протокол для функции эмбеддинга."""

    def __call__(self, texts: List[str]) -> List[List[float]]:
        """Преобразует тексты в векторы."""
        ...


def _default_embed(texts: List[str], dim: int = 64) -> List[List[float]]:
    """
    Простой эмбеддер без внешних зависимостей.
    Bag-of-words style: слова хэшируются в позиции вектора.
    Похожие тексты (общие слова) дают похожие векторы.
    """
    result = []
    for text in texts:
        vec = [0.0] * dim
        for word in (text or "").lower().split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            idx = h % dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(x * x for x in vec))
        result.append([x / norm for x in vec] if norm > 0 else vec)
    return result


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Косинусное сходство между векторами."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return min(1.0, max(0.0, dot))


class SemanticMemory:
    """
    Векторная память для поиска похожих задач.
    Хранит эмбеддинги промптов и метаданные, позволяет искать по сходству.
    """

    def __init__(
        self,
        embedder: Optional[EmbedderProtocol] = None,
        collection_name: str = "vagus_semantic",
    ):
        """
        Args:
            embedder: Функция embed(texts: List[str]) -> List[List[float]].
                     По умолчанию — простой bag-of-words.
            collection_name: Имя коллекции (для ChromaDB, если используется)
        """
        self._embedder = embedder or _default_embed
        self._collection_name = collection_name
        self._storage: Dict[str, Dict[str, Any]] = {}
        self.logger = get_logger("layer2.memory.semantic")

    def add_embedding(
        self,
        task_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Добавляет текст с эмбеддингом в память.

        Args:
            task_id: Идентификатор задачи
            text: Текст (промпт, результат)
            metadata: Дополнительные данные (result, task_type, timestamp)

        Returns:
            embedding_id — уникальный идентификатор записи
        """
        embedding_id = f"{task_id}_{uuid.uuid4().hex[:8]}"
        vectors = self._embedder([text])
        self._storage[embedding_id] = {
            "task_id": task_id,
            "text": text,
            "embedding": vectors[0],
            "metadata": metadata or {},
        }
        self.logger.debug(f"Added embedding {embedding_id} for task {task_id}")
        return embedding_id

    def search_similar(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Поиск похожих записей по запросу.

        Args:
            query: Поисковый запрос
            top_k: Максимальное количество результатов
            min_score: Минимальный порог сходства (0..1)

        Returns:
            Список dict с полями: task_id, text, score, metadata
        """
        if not self._storage:
            return []

        query_vec = self._embedder([query])[0]
        scored: List[tuple[float, Dict[str, Any]]] = []

        for emb_id, record in self._storage.items():
            score = _cosine_similarity(query_vec, record["embedding"])
            if score >= min_score:
                scored.append((score, {
                    "embedding_id": emb_id,
                    "task_id": record["task_id"],
                    "text": record["text"],
                    "score": round(score, 4),
                    "metadata": record["metadata"],
                }))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]]

    def get_context(
        self,
        query: str,
        top_k: int = 3,
        format_template: str = "Задача {task_id}: {text}\nРезультат: {result}",
    ) -> str:
        """
        Извлекает контекст из похожих задач для подстановки в промпт.

        Args:
            query: Поисковый запрос (промпт новой задачи)
            top_k: Количество похожих задач
            format_template: Шаблон для каждой записи. Доступны: task_id, text, result, metadata

        Returns:
            Отформатированная строка контекста или пустая строка
        """
        similar = self.search_similar(query, top_k=top_k)
        if not similar:
            return ""

        parts = []
        for i, item in enumerate(similar, 1):
            result = item.get("metadata", {}).get("result", "")
            if isinstance(result, dict):
                result = result.get("content", str(result)[:200])
            else:
                result = str(result)[:200]
            try:
                parts.append(format_template.format(
                    task_id=item["task_id"],
                    text=item["text"][:300],
                    result=result,
                    metadata=item.get("metadata", {}),
                ))
            except KeyError:
                parts.append(f"Похожая задача {item['task_id']}: {item['text'][:200]}")

        return "\n---\n".join(parts)

    def add_task(self, task_id: str, prompt: str, result: Any, task_type: str = "default") -> str:
        """
        Удобный метод: добавляет задачу с промптом и результатом.
        Интеграция с EpisodicMemory — результат можно взять из last_step.
        """
        return self.add_embedding(
            task_id=task_id,
            text=prompt,
            metadata={"result": result, "task_type": task_type},
        )


def sync_episodic_to_semantic(
    episodic: "EpisodicMemory",
    semantic: "SemanticMemory",
    task_id: str,
    prompt: str,
    task_type: str = "default",
) -> Optional[str]:
    """
    Синхронизация: после выполнения задачи добавляет её в SemanticMemory.
    Берёт результат из последнего шага EpisodicMemory.

    Args:
        episodic: EpisodicMemory с историей
        semantic: SemanticMemory для векторного поиска
        task_id: Идентификатор задачи
        prompt: Промпт задачи
        task_type: Тип задачи

    Returns:
        embedding_id или None если нет результата
    """
    last = episodic.get_last_step(task_id)
    if not last:
        return None
    result = last.get("result", {})
    return semantic.add_task(task_id=task_id, prompt=prompt, result=result, task_type=task_type)


__all__ = ["SemanticMemory", "EmbedderProtocol", "_default_embed", "sync_episodic_to_semantic"]
