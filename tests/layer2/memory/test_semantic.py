"""Тесты SemanticMemory (async API, tenant_id, ChromaDB)."""

import pytest

chromadb = pytest.importorskip("chromadb")

from vagus.layer2.memory.semantic import SemanticMemory


@pytest.fixture
def memory():
    """SemanticMemory с EphemeralClient."""
    client = chromadb.EphemeralClient()
    return SemanticMemory(chroma_client=client)


@pytest.mark.asyncio
async def test_initialize_creates_collection(memory):
    """initialize создаёт _async_collection."""
    await memory.initialize()
    assert memory._async_collection is not None
    assert memory._async_initialized is True


@pytest.mark.asyncio
async def test_add_document_returns_id(memory):
    """add_document_async возвращает UUID, запись в коллекции."""
    doc_id = await memory.add_document_async(
        "test document text",
        {"tenant_id": "tenant1"},
    )
    assert doc_id
    assert len(doc_id) == 36


@pytest.mark.asyncio
async def test_add_document_requires_tenant_id(memory):
    """add_document_async требует tenant_id в metadata."""
    with pytest.raises(ValueError, match="tenant_id"):
        await memory.add_document_async("text", {})


@pytest.mark.asyncio
async def test_search_filters_by_tenant(memory):
    """search_async фильтрует по tenant_id."""
    await memory.add_document_async("doc a", {"tenant_id": "tenant_a"})
    await memory.add_document_async("doc b", {"tenant_id": "tenant_b"})
    results_a = await memory.search_async("doc", "tenant_a", top_k=5)
    results_b = await memory.search_async("doc", "tenant_b", top_k=5)
    assert len(results_a) == 1
    assert len(results_b) == 1
    assert results_a[0]["text"] == "doc a"
    assert results_b[0]["text"] == "doc b"


@pytest.mark.asyncio
async def test_search_returns_text_and_metadata(memory):
    """search_async возвращает структуру с text и metadata."""
    await memory.add_document_async(
        "hello world",
        {"tenant_id": "t1", "task_type": "code"},
    )
    results = await memory.search_async("hello", "t1", top_k=1)
    assert len(results) == 1
    assert "text" in results[0]
    assert "metadata" in results[0]
    assert results[0]["text"] == "hello world"
    assert results[0]["metadata"].get("tenant_id") == "t1"
