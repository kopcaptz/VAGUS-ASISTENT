"""Unit-тесты SemanticMemory."""
import pytest

from vagus.layer2.memory import SemanticMemory


def test_add_embedding_returns_id():
    """add_embedding возвращает embedding_id."""
    memory = SemanticMemory()
    emb_id = memory.add_embedding("task1", "Напиши код на Python", {"task_type": "code"})
    assert emb_id
    assert "task1" in emb_id


def test_search_similar_empty():
    """search_similar на пустой памяти возвращает []."""
    memory = SemanticMemory()
    assert memory.search_similar("любой запрос") == []


def test_search_similar_finds_same():
    """search_similar находит запись с тем же текстом."""
    memory = SemanticMemory()
    memory.add_embedding("t1", "Напиши функцию сложения", {"task_type": "code"})
    results = memory.search_similar("Напиши функцию сложения", top_k=1)
    assert len(results) == 1
    assert results[0]["task_id"] == "t1"
    assert results[0]["score"] >= 0.99


def test_search_similar_semantic():
    """Похожие по смыслу тексты получают высокий score."""
    memory = SemanticMemory()
    memory.add_embedding("t1", "напиши код для сложения чисел", {"result": "def add"})
    results = memory.search_similar("код сложения чисел", top_k=1)
    assert len(results) == 1
    assert results[0]["score"] > 0.5


def test_search_similar_top_k():
    """search_similar ограничивает количество результатов."""
    memory = SemanticMemory()
    for i in range(5):
        memory.add_embedding(f"t{i}", f"задача номер {i} программирование", {})
    results = memory.search_similar("программирование", top_k=2)
    assert len(results) == 2


def test_get_context():
    """get_context возвращает отформатированный контекст."""
    memory = SemanticMemory()
    memory.add_embedding("t1", "сложи два числа", metadata={"result": {"content": "def add"}})
    ctx = memory.get_context("сложи числа", top_k=1)
    assert "t1" in ctx
    assert "сложи" in ctx or "add" in ctx


def test_get_context_empty():
    """get_context на пустой памяти возвращает ''."""
    memory = SemanticMemory()
    assert memory.get_context("запрос") == ""


def test_add_task():
    """add_task добавляет задачу с результатом."""
    memory = SemanticMemory()
    emb_id = memory.add_task(
        "task1",
        "Напиши скрипт",
        {"content": "код готов", "success": True},
        task_type="code",
    )
    assert emb_id
    results = memory.search_similar("скрипт", top_k=1)
    assert results[0]["metadata"]["result"]["success"] is True
