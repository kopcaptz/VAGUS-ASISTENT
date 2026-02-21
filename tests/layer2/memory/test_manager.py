"""Тесты MemoryManager."""

import json
import pytest

from vagus.layer2.memory import (
    ArtifactKnowledgeBase,
    EpisodicMemory,
    MemoryManager,
    ProceduralMemory,
    SemanticMemory,
)


def test_memory_manager_init():
    """MemoryManager инициализируется с параметрами по умолчанию."""
    mgr = MemoryManager()
    assert mgr._episodic is None
    assert mgr._semantic is None
    assert mgr._procedural is None
    assert mgr._artifact_kb is None


def test_memory_manager_init_with_injection():
    """MemoryManager с injection возвращает переданный artifact_kb."""
    kb = ArtifactKnowledgeBase(":memory:")
    mgr = MemoryManager(artifact_kb=kb)
    assert mgr.artifact_kb is kb


def test_memory_manager_episodic_lazy():
    """Episodic memory создаётся лениво при обращении."""
    mgr = MemoryManager()
    assert mgr._episodic is None
    _ = mgr.episodic
    assert mgr._episodic is not None


def test_memory_manager_semantic_lazy():
    """Semantic memory создаётся лениво при обращении."""
    mgr = MemoryManager()
    assert mgr._semantic is None
    _ = mgr.semantic
    assert mgr._semantic is not None


def test_memory_manager_procedural_lazy():
    """Procedural memory создаётся лениво при обращении."""
    mgr = MemoryManager()
    assert mgr._procedural is None
    _ = mgr.procedural
    assert mgr._procedural is not None


def test_memory_manager_artifact_kb_lazy():
    """ArtifactKnowledgeBase создаётся лениво при обращении."""
    mgr = MemoryManager()
    assert mgr._artifact_kb is None
    _ = mgr.artifact_kb
    assert mgr._artifact_kb is not None


def test_memory_manager_store_not_implemented():
    """store() поднимает NotImplementedError (заглушка)."""
    from vagus.layer2.memory import MemoryEntry

    mgr = MemoryManager()
    entry = MemoryEntry(id="e1", content="test")
    with pytest.raises(NotImplementedError, match="в разработке"):
        mgr.store(entry)


def test_memory_manager_search_not_implemented():
    """search() поднимает NotImplementedError (заглушка)."""
    mgr = MemoryManager()
    with pytest.raises(NotImplementedError, match="в разработке"):
        mgr.search("query")


@pytest.mark.asyncio
async def test_get_context_for_task():
    """get_context_for_task возвращает структуру контекста с history, relevant_knowledge, similar_plans, tenant_id, task_id."""
    mgr = MemoryManager()
    ctx = await mgr.get_context_for_task(
        {"task_id": "t1", "description": "test task", "intent_summary": ""}, "tenant1"
    )
    assert "history" in ctx
    assert ctx["history"] == []
    assert "relevant_knowledge" in ctx
    assert "similar_plans" in ctx
    assert ctx["similar_plans"] == []
    assert ctx["tenant_id"] == "tenant1"
    assert ctx["task_id"] == "t1"


@pytest.mark.asyncio
async def test_get_context_for_task_with_episodic_history():
    """get_context_for_task возвращает историю из EpisodicMemory."""
    episodic = EpisodicMemory(":memory:")
    mgr = MemoryManager(episodic_memory=episodic)
    await episodic.add_step_async(
        "tenant_a", "task_1", "coder", "execute", {"output": "ok"}, {}
    )
    ctx = await mgr.get_context_for_task(
        {"task_id": "task_1", "description": ""}, "tenant_a"
    )
    assert len(ctx["history"]) == 1
    assert ctx["history"][0]["agent_type"] == "coder"
    assert ctx["history"][0]["action"] == "execute"
    assert ctx["history"][0]["result"] == {"output": "ok"}


@pytest.mark.asyncio
async def test_get_context_for_task_with_semantic_knowledge():
    """get_context_for_task возвращает relevant_knowledge из SemanticMemory."""
    chromadb = pytest.importorskip("chromadb")
    semantic = SemanticMemory(chroma_client=chromadb.EphemeralClient())
    mgr = MemoryManager(semantic_memory=semantic)
    await semantic.add_document_async("Python code for parsing JSON", {"tenant_id": "t1"})
    ctx = await mgr.get_context_for_task(
        {"task_id": "x", "description": "Python JSON parsing"}, "t1"
    )
    assert len(ctx["relevant_knowledge"]) >= 1
    assert "text" in ctx["relevant_knowledge"][0]
    assert "metadata" in ctx["relevant_knowledge"][0]


@pytest.mark.asyncio
async def test_get_context_for_task_with_similar_plan():
    """get_context_for_task возвращает similar_plans из ProceduralMemory."""
    procedural = ProceduralMemory(":memory:")
    mgr = MemoryManager(procedural_memory=procedural)
    plan_json = json.dumps({"steps": [{"agent_type": "researcher", "prompt": "search"}]})
    await procedural.save_plan("t1", "search web analyze", plan_json, success_score=0.9)
    ctx = await mgr.get_context_for_task(
        {"task_id": "x", "intent_summary": "search web analyze"}, "t1"
    )
    assert len(ctx["similar_plans"]) == 1
    assert "steps" in ctx["similar_plans"][0]
    assert ctx["similar_plans"][0]["steps"][0]["agent_type"] == "researcher"


@pytest.mark.asyncio
async def test_save_episodic_step():
    """save_episodic_step делегирует в episodic.add_step_async, шаг появляется в get_context_for_task."""
    episodic = EpisodicMemory(":memory:")
    mgr = MemoryManager(episodic_memory=episodic)
    step_id = await mgr.save_episodic_step(
        "tenant1", "task_42", "analyst", "analyze", {"findings": "x"}, {"source": "step1"}
    )
    assert step_id
    assert len(step_id) == 32
    ctx = await mgr.get_context_for_task(
        {"task_id": "task_42", "description": ""}, "tenant1"
    )
    assert len(ctx["history"]) == 1
    assert ctx["history"][0]["step_id"] == step_id
    assert ctx["history"][0]["agent_type"] == "analyst"
    assert ctx["history"][0]["action"] == "analyze"
    assert ctx["history"][0]["metadata"] == {"source": "step1"}


@pytest.mark.asyncio
async def test_save_artifact_delegates():
    """save_artifact делегирует в artifact_kb, возвращает artifact_id."""
    kb = ArtifactKnowledgeBase(":memory:")
    mgr = MemoryManager(artifact_kb=kb)
    artifact_id = await mgr.save_artifact(
        "code content", "code", "step-1", "tenant1"
    )
    assert artifact_id
    assert len(artifact_id) == 36
    async with kb._conn.execute(
        "SELECT 1 FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_link_artifacts_delegates():
    """link_artifacts делегирует в artifact_kb.link_artifacts."""
    kb = ArtifactKnowledgeBase(":memory:")
    mgr = MemoryManager(artifact_kb=kb)
    id1 = await mgr.save_artifact("a", "code", "s1", "t1")
    id2 = await mgr.save_artifact("b", "code", "s2", "t1")
    await mgr.link_artifacts(id1, id2, "t1")
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert w == 0.5
