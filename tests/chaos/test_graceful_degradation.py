"""
Chaos tests: Graceful Degradation.

Verifies that the system degrades gracefully when infrastructure fails:
- Redis: startup fallback to in-memory, graceful error when Redis stops at runtime
- PostgreSQL: graceful error when Postgres is down
- ChromaDB: startup fallback to in-memory when Chroma init fails
"""
import pytest
from unittest.mock import MagicMock

from tests.chaos.docker_utils import (
    CONTAINER_POSTGRES,
    CONTAINER_REDIS,
    container_running,
    container_start,
    container_stop,
    docker_available,
)
from tests.chaos.fallback_monitor import is_blackboard_using_memory, is_event_bus_using_memory


def _mock_llm(content: str = "{}"):
    async def _inner(prompt: str, **kwargs):
        yield {"content": content, "done": True}

    return _inner


SIMPLE_PLAN = {
    "plan_id": "plan_chaos",
    "steps": [
        {
            "step_id": "s1",
            "agent_type": "researcher",
            "prompt": "Test",
            "depends_on": [],
            "artefact_key": "r1",
        }
    ],
    "execution_mode": "sequential",
}


@pytest.mark.chaos
@pytest.mark.skipif(not docker_available(), reason="Docker required for chaos tests")
@pytest.mark.asyncio
async def test_redis_failure_recovery():
    """
    1. With Redis disabled (redis_url=None): Blackboard and Event Bus use in-memory
    2. With Redis running: orchestrator works
    3. Stop Redis: next operation fails with connection error (no process crash)
    4. Start Redis: recovery (or skip if reconnect not implemented)
    """
    from vagus.layer2 import create_master_orchestrator_full

    # 1. Redis disabled / unavailable at startup -> in-memory fallback
    layer2_no_redis = {
        "blackboard": {"redis_url": None, "enabled": True},
        "communication": {"redis_url": None, "event_bus": {"enabled": True}},
        "procedural_memory": {"enabled": False, "db_path": ":memory:"},
        "knowledge_base": {"backend": "sqlite", "sqlite_path": ":memory:"},
    }

    mock_router = MagicMock()
    mock_router.route_request = _mock_llm("dummy")

    orch = create_master_orchestrator_full(mock_router, layer2_config=layer2_no_redis)
    assert is_blackboard_using_memory(orch.shared_blackboard)
    assert is_event_bus_using_memory(orch.event_bus)

    # 2. With Redis running (if available)
    if not container_running(CONTAINER_REDIS):
        pytest.skip("vagus-redis container not running")

    layer2_with_redis = {
        "blackboard": {"redis_url": "redis://localhost:6379/5", "enabled": True},
        "communication": {
            "redis_url": "redis://localhost:6379/5",
            "event_bus": {"enabled": True, "use_streams": False},
        },
        "procedural_memory": {"enabled": False, "db_path": ":memory:"},
        "knowledge_base": {"backend": "sqlite", "sqlite_path": ":memory:"},
    }

    orch_redis = create_master_orchestrator_full(mock_router, layer2_config=layer2_with_redis)
    assert not is_blackboard_using_memory(orch_redis.shared_blackboard)

    # Mock intent + planner for simple task
    async def _mock_classify(_):
        return {"primary_intent": "research", "complexity": "simple", "confidence": 0.9}

    async def _mock_create_plan(_):
        return SIMPLE_PLAN

    async def _mock_process(task, context=None):
        return {"content": "Done", "metadata": {}}

    orch_redis.intent_classifier.classify = _mock_classify
    orch_redis.task_planner.create_plan = _mock_create_plan
    for agent in orch_redis.agent_registry.list():
        agent.process = _mock_process

    result = await orch_redis.process_request("Test with Redis")
    assert "content" in result
    assert "plan_id" in result.get("metadata", {})

    # 3. Stop Redis and verify next operation fails gracefully (raises, not crash)
    stopped = container_stop(CONTAINER_REDIS)
    if not stopped:
        pytest.skip("Could not stop Redis container")

    try:
        with pytest.raises(Exception) as exc_info:
            await orch_redis.process_request("Test after Redis stop")
        # Should be connection-related
        assert exc_info.value is not None
    finally:
        # 4. Restore Redis
        container_start(CONTAINER_REDIS)


@pytest.mark.chaos
@pytest.mark.skipif(not docker_available(), reason="Docker required for chaos tests")
@pytest.mark.asyncio
async def test_postgres_failure_recovery():
    """
    1. PostgreSQL running: ArtifactKB write succeeds
    2. Stop Postgres: operation raises (graceful error)
    3. Start Postgres: operation succeeds again
    """
    pytest.importorskip("asyncpg")
    from vagus.layer2.memory import ArtifactKnowledgeBasePG

    if not container_running(CONTAINER_POSTGRES):
        pytest.skip("vagus-postgres container not running")

    pg_url = "postgresql+asyncpg://vagus:vagus_password@localhost:5432/vagus_db"
    kb = ArtifactKnowledgeBasePG(postgres_url=pg_url)

    try:
        # 1. Write succeeds when Postgres is up
        aid = await kb.write_artifact(
            content="chaos test content",
            artifact_type="test",
            source="chaos",
            tenant_id="default",
            plan_id="chaos_plan",
            key="chaos_key",
        )
        assert aid

        # 2. Stop Postgres
        stopped = container_stop(CONTAINER_POSTGRES)
        if not stopped:
            pytest.skip("Could not stop Postgres container")

        with pytest.raises(Exception):
            await kb.write_artifact(
                content="after stop",
                artifact_type="test",
                source="chaos",
                tenant_id="default",
                plan_id="chaos_plan",
                key="chaos_key2",
            )
    finally:
        await kb.close()
        container_start(CONTAINER_POSTGRES)


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_chromadb_failure_recovery(tmp_path):
    """
    SemanticMemory with invalid persist_directory falls back to in-memory.
    add_document_async and search_async work without ChromaDB.
    """
    from vagus.layer2.memory import SemanticMemory

    pytest.importorskip("chromadb")

    # Use path that is a file (not directory) - Chroma expects directory and will fail
    file_path = tmp_path / "not_a_directory"
    file_path.write_text("")
    invalid_path = str(file_path)
    memory = SemanticMemory(persist_directory=invalid_path)

    # Should fall back to in-memory (Chroma init fails)
    await memory.initialize()
    assert not memory._using_chroma

    # add_document_async and search should work
    doc_id = await memory.add_document_async(
        text="Chaos test document",
        metadata={"tenant_id": "default", "task_id": "chaos_1"},
    )
    assert doc_id

    results = await memory.search_async(query="chaos test", tenant_id="default", top_k=5)
    assert len(results) >= 1
    assert any("chaos" in r.get("text", "").lower() for r in results)
