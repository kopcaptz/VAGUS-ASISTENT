"""Тесты SemanticMemory для ChromaDB и in-memory режимов."""

import pytest

from vagus.layer2.memory.semantic import SemanticMemory, _default_embed
import vagus.layer2.memory.semantic as semantic_module


def test_document_api_in_memory_mode():
    """Публичный document API работает в fallback in-memory режиме."""
    memory = SemanticMemory()
    memory.add_document("doc_1", "python функция сложения", {"source": "unit"})
    memory.add_document("doc_2", "рецепт пасты", {"source": "unit"})

    results = memory.search("python код сложения", top_k=2)

    assert memory.get_document_count() == 2
    assert len(results) == 2
    assert results[0][0] == "doc_1"
    assert results[0][1] >= results[1][1]
    assert results[0][2]["source"] == "unit"

    memory.clear()
    assert memory.get_document_count() == 0
    assert memory.search("python") == []


def test_document_api_chroma_mode(monkeypatch):
    """Document API работает через Chroma backend."""
    chromadb = pytest.importorskip("chromadb")
    monkeypatch.setattr(semantic_module, "SentenceTransformerEmbeddingFunction", None)

    client = chromadb.EphemeralClient()
    memory = SemanticMemory(chroma_client=client, embedder=_default_embed)
    memory.add_document("doc_a", "python функция сложения", {"topic": "code"})
    memory.add_document("doc_b", "футбольный матч", {"topic": "sport"})

    results = memory.search("python сложение", top_k=2)
    assert memory.get_document_count() == 2
    assert len(results) == 2
    assert results[0][0] == "doc_a"
    assert results[0][2]["topic"] == "code"

    memory.clear()
    assert memory.get_document_count() == 0


def test_chroma_path_and_backward_compat_methods(tmp_path, monkeypatch):
    """chroma_path создает persistent client, старые методы продолжают работать."""
    pytest.importorskip("chromadb")
    monkeypatch.setattr(semantic_module, "SentenceTransformerEmbeddingFunction", None)

    chroma_path = tmp_path / "chroma"
    memory = SemanticMemory(chroma_path=str(chroma_path), embedder=_default_embed)

    emb_id = memory.add_embedding("task42", "создай функцию суммы", {"task_type": "code"})
    similar = memory.search_similar("функция суммы", top_k=1)

    assert emb_id
    assert memory.get_document_count() == 1
    assert len(similar) == 1
    assert similar[0]["task_id"] == "task42"
