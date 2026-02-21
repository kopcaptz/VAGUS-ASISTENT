"""
SemanticMemory — векторное хранилище для долгосрочной памяти.
Поиск похожих задач по эмбеддингам промптов.
"""

import asyncio
import hashlib
import math
import random
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple

if TYPE_CHECKING:
    from .episodic import EpisodicMemory

from ...layer0.logging import get_logger

try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
except Exception:
    chromadb = None
    SentenceTransformerEmbeddingFunction = None


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


def _generate_embedding(text: str) -> List[float]:
    """Заглушка: возвращает нормализованный случайный вектор 384-dim."""
    vec = [random.random() for _ in range(384)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec


class SemanticMemory:
    """
    Векторная память для поиска похожих задач.
    Хранит эмбеддинги промптов и метаданные, позволяет искать по сходству.
    """

    def __init__(
        self,
        embedder: Optional[EmbedderProtocol] = None,
        collection_name: str = "vagus_semantic_memory",
        chroma_client: Optional[Any] = None,
        chroma_path: Optional[str] = None,
        persist_directory: Optional[str] = None,
    ):
        """
        Args:
            embedder: Функция embed(texts: List[str]) -> List[List[float]].
                     По умолчанию — простой bag-of-words.
            collection_name: Имя коллекции (для ChromaDB, если используется)
            chroma_client: Готовый клиент ChromaDB (опционально)
            chroma_path: Путь для PersistentClient ChromaDB (deprecated, используйте persist_directory)
            persist_directory: Путь для PersistentClient ChromaDB (опционально)
        """
        self._embedder = embedder or _default_embed
        self._collection_name = collection_name
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._embedding_cache: Dict[str, List[float]] = {}
        self._chroma_client = None
        self._chroma_collection = None
        self._chroma_embed_with_sentence_transformer = False
        self.persist_directory = persist_directory or chroma_path
        self._client = chroma_client
        self._collection = None
        self._async_initialized = False
        self._async_collection = None  # коллекция для async API (384-dim)
        self.logger = get_logger("layer2.memory.semantic")

        if chroma_client is None and chroma_path and chromadb is not None:
            try:
                chroma_client = chromadb.PersistentClient(path=chroma_path)
                self._client = chroma_client
            except Exception as exc:
                self.logger.warning(
                    "Failed to initialize Chroma PersistentClient at %s: %s. Falling back to in-memory mode.",
                    chroma_path,
                    exc,
                )

        if chroma_client is not None:
            self._client = chroma_client
            self._setup_chroma_backend(chroma_client)

    @property
    def _using_chroma(self) -> bool:
        return self._chroma_collection is not None

    def _setup_chroma_backend(self, chroma_client: Any) -> None:
        if chromadb is None:
            self.logger.warning(
                "Chroma client provided but chromadb is unavailable. Falling back to in-memory mode."
            )
            return

        collection_kwargs: Dict[str, Any] = {
            "name": self._collection_name,
            "metadata": {"hnsw:space": "cosine"},
        }
        if SentenceTransformerEmbeddingFunction is not None:
            try:
                collection_kwargs["embedding_function"] = SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
                self._chroma_embed_with_sentence_transformer = True
            except Exception as exc:
                self.logger.warning(
                    "Failed to initialize SentenceTransformerEmbeddingFunction: %s. "
                    "Using local fallback embedder for Chroma.",
                    exc,
                )

        try:
            self._chroma_client = chroma_client
            self._chroma_collection = self._chroma_client.get_or_create_collection(
                **collection_kwargs
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to initialize Chroma collection '%s': %s. Falling back to in-memory mode.",
                self._collection_name,
                exc,
            )
            self._chroma_client = None
            self._chroma_collection = None
            self._chroma_embed_with_sentence_transformer = False

    async def initialize(self) -> None:
        """Инициализирует ChromaDB клиент и коллекцию (lazy)."""
        if self._async_initialized:
            return
        if self._client is None and self.persist_directory and chromadb is not None:
            try:
                self._client = await asyncio.to_thread(
                    chromadb.PersistentClient, path=self.persist_directory
                )
                self._setup_chroma_backend(self._client)
            except Exception as exc:
                self.logger.warning(
                    "Failed to initialize Chroma at %s: %s. Using in-memory fallback.",
                    self.persist_directory,
                    exc,
                )
        client = self._client or self._chroma_client
        if client is not None and chromadb is not None:
            self._async_collection = await asyncio.to_thread(
                client.get_or_create_collection,
                name=f"{self._collection_name}_async",
                metadata={"hnsw:space": "cosine"},
            )
        self._async_initialized = True

    async def add_document_async(
        self,
        text: str,
        metadata: dict,
        embedding: Optional[List[float]] = None,
    ) -> str:
        """
        Добавляет документ в коллекцию (async).
        metadata должен содержать tenant_id.

        Returns:
            doc_id — UUID документа
        """
        await self.initialize()
        if "tenant_id" not in metadata:
            raise ValueError("metadata must contain 'tenant_id'")
        doc_id = str(uuid.uuid4())
        emb = embedding if embedding is not None else _generate_embedding(text)

        if self._async_collection is not None:
            meta_ser = {}
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta_ser[k] = v
                else:
                    meta_ser[k] = str(v)

            def _add() -> None:
                self._async_collection.add(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[meta_ser],
                    embeddings=[emb],
                )

            await asyncio.to_thread(_add)
        else:
            self._storage[doc_id] = {
                "text": text,
                "embedding": emb,
                "metadata": metadata,
                "task_id": metadata.get("task_id", doc_id),
            }
        return doc_id

    async def search_async(
        self, query: str, tenant_id: str, top_k: int = 5
    ) -> List[dict]:
        """
        Ищет документы с фильтром tenant_id.

        Returns:
            Список [{"text": ..., "metadata": ...}, ...]
        """
        await self.initialize()
        if self._async_collection is not None:

            def _query() -> Any:
                return self._async_collection.query(
                    query_embeddings=[_generate_embedding(query)],
                    n_results=top_k,
                    where={"tenant_id": tenant_id},
                    include=["documents", "metadatas"],
                )

            result = await asyncio.to_thread(_query)
            docs = result.get("documents", [[]])[0] or []
            metas = result.get("metadatas", [[]])[0] or []
            return [
                {"text": doc or "", "metadata": meta or {}}
                for doc, meta in zip(docs, metas)
            ]

        if not self._storage:
            return []
        query_vec = _generate_embedding(query)
        scored: List[tuple[float, str, Dict[str, Any]]] = []
        for doc_id, record in self._storage.items():
            if record.get("metadata", {}).get("tenant_id") != tenant_id:
                continue
            score = _cosine_similarity(query_vec, record["embedding"])
            scored.append((score, record["text"], record["metadata"]))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"text": t, "metadata": m} for _, t, m in scored[:top_k]]

    @staticmethod
    def _distance_to_score(distance: Optional[float]) -> float:
        if distance is None:
            return 0.0
        # Для cosine distance в Chroma меньше — лучше. Нормируем в [0..1].
        return min(1.0, max(0.0, 1.0 - float(distance)))

    def add_document(self, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Добавляет документ в память."""
        meta = dict(metadata or {})

        if self._using_chroma:
            if self._chroma_embed_with_sentence_transformer:
                self._chroma_collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
            else:
                self._chroma_collection.upsert(
                    ids=[doc_id],
                    documents=[text],
                    metadatas=[meta],
                    embeddings=self._embedder([text]),
                )
            return

        self._storage[doc_id] = {
            "task_id": meta.get("task_id", doc_id),
            "text": text,
            "embedding": self._embedder([text])[0],
            "metadata": meta,
        }

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
        meta = dict(metadata or {})
        meta["task_id"] = task_id
        self.add_document(embedding_id, text, meta)
        self.logger.debug(f"Added embedding {embedding_id} for task {task_id}")
        return embedding_id

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Унифицированный поиск:
        Returns: List[(doc_id, score, metadata)]
        """
        if self._using_chroma:
            if self.get_document_count() == 0:
                return []
            query_kwargs: Dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
                "include": ["metadatas", "distances"],
            }
            if not self._chroma_embed_with_sentence_transformer:
                query_kwargs["query_embeddings"] = self._embedder([query])
                query_kwargs.pop("query_texts", None)
            result = self._chroma_collection.query(**query_kwargs)
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            return [
                (
                    doc_id,
                    round(self._distance_to_score(distance), 4),
                    metadata or {},
                )
                for doc_id, distance, metadata in zip(ids, distances, metadatas)
            ]

        if not self._storage:
            return []

        cache_key = f"q:{hashlib.md5(query.encode()).hexdigest()}"
        if cache_key in self._embedding_cache:
            query_vec = self._embedding_cache[cache_key]
        else:
            query_vec = self._embedder([query])[0]
            self._embedding_cache[cache_key] = query_vec

        scored: List[Tuple[str, float, Dict[str, Any]]] = []
        for doc_id, record in self._storage.items():
            score = _cosine_similarity(query_vec, record["embedding"])
            scored.append((doc_id, round(score, 4), record["metadata"]))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

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
        if self._using_chroma:
            if self.get_document_count() == 0:
                return []

            query_kwargs: Dict[str, Any] = {
                "query_texts": [query],
                "n_results": top_k,
                "include": ["metadatas", "distances", "documents"],
            }
            if not self._chroma_embed_with_sentence_transformer:
                query_kwargs["query_embeddings"] = self._embedder([query])
                query_kwargs.pop("query_texts", None)

            result = self._chroma_collection.query(**query_kwargs)
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            documents = result.get("documents", [[]])[0]

            items: List[Dict[str, Any]] = []
            for emb_id, distance, metadata, doc_text in zip(ids, distances, metadatas, documents):
                score = round(self._distance_to_score(distance), 4)
                if score < min_score:
                    continue
                meta = metadata or {}
                items.append(
                    {
                        "embedding_id": emb_id,
                        "task_id": meta.get("task_id", emb_id),
                        "text": doc_text or "",
                        "score": score,
                        "metadata": meta,
                    }
                )
            return items

        if not self._storage:
            return []

        cache_key = f"q:{hashlib.md5(query.encode()).hexdigest()}"
        if cache_key in self._embedding_cache:
            query_vec = self._embedding_cache[cache_key]
        else:
            query_vec = self._embedder([query])[0]
            self._embedding_cache[cache_key] = query_vec
        scored: List[tuple[float, Dict[str, Any]]] = []

        for emb_id, record in self._storage.items():
            score = _cosine_similarity(query_vec, record["embedding"])
            if score >= min_score:
                scored.append(
                    (
                        score,
                        {
                            "embedding_id": emb_id,
                            "task_id": record["task_id"],
                            "text": record["text"],
                            "score": round(score, 4),
                            "metadata": record["metadata"],
                        },
                    )
                )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]]

    def clear(self) -> None:
        """Полностью очищает память."""
        if self._using_chroma:
            try:
                self._chroma_client.delete_collection(name=self._collection_name)
            except Exception:
                pass
            self._setup_chroma_backend(self._chroma_client)
            return

        self._storage.clear()
        self._embedding_cache.clear()

    def get_document_count(self) -> int:
        """Возвращает количество документов в памяти."""
        if self._using_chroma:
            return int(self._chroma_collection.count())
        return len(self._storage)

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

    def add_task(
        self,
        task_id: str,
        prompt: str,
        result: Any,
        task_type: str = "default",
        tenant_id: str = "default",
    ) -> str:
        """
        Удобный метод: добавляет задачу с промптом и результатом.
        Интеграция с EpisodicMemory — результат можно взять из last_step.
        tenant_id требуется для search_async.
        """
        return self.add_embedding(
            task_id=task_id,
            text=prompt,
            metadata={"result": result, "task_type": task_type, "tenant_id": tenant_id},
        )


def sync_episodic_to_semantic(
    episodic: "EpisodicMemory",
    semantic: "SemanticMemory",
    task_id: str,
    prompt: str,
    task_type: str = "default",
    tenant_id: str = "default",
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
        tenant_id: Идентификатор tenant

    Returns:
        embedding_id или None если нет результата
    """
    last = episodic.get_last_step(task_id, tenant_id)
    if not last:
        return None
    result = last.get("result", {})
    return semantic.add_task(
        task_id=task_id,
        prompt=prompt,
        result=result,
        task_type=task_type,
        tenant_id=tenant_id,
    )


__all__ = ["SemanticMemory", "EmbedderProtocol", "_default_embed", "sync_episodic_to_semantic"]
