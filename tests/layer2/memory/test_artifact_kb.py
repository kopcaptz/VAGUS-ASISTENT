"""Тесты ArtifactKnowledgeBase."""

import pytest

from vagus.layer2.memory import (
    ArtifactKnowledgeBase,
    ArtifactNotFoundError,
    ArtifactRecord,
)


@pytest.fixture
def kb():
    """ArtifactKnowledgeBase с in-memory БД."""
    return ArtifactKnowledgeBase(db_path=":memory:")


@pytest.fixture
def sample_artifact():
    """Пример артефакта."""
    return ArtifactRecord(
        id="art-001",
        artifact_type="code",
        content="def hello(): print('world')",
        metadata={"language": "python"},
        task_id="task-1",
        agent_type="coder",
    )


@pytest.mark.asyncio
async def test_artifact_kb_add_not_implemented(kb, sample_artifact):
    """add() поднимает NotImplementedError (заглушка)."""
    with pytest.raises(NotImplementedError, match="в разработке"):
        await kb.add(sample_artifact)


@pytest.mark.asyncio
async def test_artifact_kb_search_not_implemented(kb):
    """search() поднимает NotImplementedError (заглушка)."""
    with pytest.raises(NotImplementedError, match="в разработке"):
        await kb.search("query")


@pytest.mark.asyncio
async def test_artifact_kb_get_by_id_not_implemented(kb):
    """get_by_id() поднимает NotImplementedError (заглушка)."""
    with pytest.raises(NotImplementedError, match="в разработке"):
        await kb.get_by_id("art-001")


@pytest.mark.asyncio
async def test_artifact_kb_init_db_creates_tables(kb):
    """_ensure_initialized создаёт таблицы artifacts и artifact_relationships."""
    await kb._ensure_initialized()
    assert kb._initialized is True
    assert kb._conn is not None
    async with kb._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cur:
        tables = [row[0] for row in await cur.fetchall()]
    assert "artifacts" in tables
    assert "artifact_relationships" in tables


@pytest.mark.asyncio
async def test_write_artifact_returns_id(kb):
    """write_artifact возвращает UUID artifact_id, запись есть в таблице."""
    artifact_id = await kb.write_artifact(
        "hello", "code", "test_source", "tenant1"
    )
    assert artifact_id
    assert len(artifact_id) == 36
    assert artifact_id.count("-") == 4
    async with kb._conn.execute(
        "SELECT 1 FROM artifacts WHERE artifact_id = ?", (artifact_id,)
    ) as cur:
        row = await cur.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_write_artifact_persists_content(kb):
    """write_artifact сохраняет content_json и artifact_type."""
    content = "def hello(): pass"
    artifact_id = await kb.write_artifact(
        content, "document", "src", "tenant1"
    )
    async with kb._conn.execute(
        "SELECT content_json, artifact_type FROM artifacts WHERE artifact_id = ?",
        (artifact_id,),
    ) as cur:
        row = await cur.fetchone()
    assert row is not None
    assert content in row[0]
    assert row[1] == "document"


@pytest.mark.asyncio
async def test_get_artifact_id_by_plan_key(kb):
    """get_artifact_id_by_plan_key возвращает artifact_id по tenant, plan_id, key."""
    artifact_id = await kb.write_artifact(
        "content", "code", "source", "t1", plan_id="plan_1", key="art_1"
    )
    found = await kb.get_artifact_id_by_plan_key("t1", "plan_1", "art_1")
    assert found == artifact_id
    assert await kb.get_artifact_id_by_plan_key("t1", "plan_1", "nonexistent") is None
    assert await kb.get_artifact_id_by_plan_key("t1", "other_plan", "art_1") is None


@pytest.mark.asyncio
async def test_link_artifacts_creates_relationship(kb):
    """link_artifacts создаёт запись в artifact_relationships."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    await kb.link_artifacts(id1, id2, "t1")
    async with kb._conn.execute(
        "SELECT COUNT(*) FROM artifact_relationships "
        "WHERE source_id = ? AND target_id = ? AND tenant_id = ?",
        (id1, id2, "t1"),
    ) as cur:
        (count,) = await cur.fetchone()
    assert count == 1


@pytest.mark.asyncio
async def test_link_artifacts_duplicate_ignored(kb):
    """Повторный link_artifacts с теми же параметрами не создаёт дубликат."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    await kb.link_artifacts(id1, id2, "t1")
    await kb.link_artifacts(id1, id2, "t1")
    async with kb._conn.execute(
        "SELECT COUNT(*) FROM artifact_relationships WHERE tenant_id = ?", ("t1",)
    ) as cur:
        (count,) = await cur.fetchone()
    assert count == 1


@pytest.mark.asyncio
async def test_link_artifacts_raises_if_source_missing(kb):
    """link_artifacts поднимает ArtifactNotFoundError при несуществующем source_id."""
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    with pytest.raises(ArtifactNotFoundError, match="Artifact not found: non-existent"):
        await kb.link_artifacts("non-existent", id2, "t1")


@pytest.mark.asyncio
async def test_link_artifacts_raises_if_target_missing(kb):
    """link_artifacts поднимает ArtifactNotFoundError при несуществующем target_id."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    with pytest.raises(ArtifactNotFoundError, match="Artifact not found: non-existent"):
        await kb.link_artifacts(id1, "non-existent", "t1")


@pytest.mark.asyncio
async def test_artifact_exists(kb):
    """_artifact_exists возвращает True для существующего, False для отсутствующего."""
    artifact_id = await kb.write_artifact("x", "code", "src", "t1")
    assert await kb._artifact_exists(artifact_id, "t1") is True
    assert await kb._artifact_exists("missing-uuid", "t1") is False
    assert await kb._artifact_exists(artifact_id, "other_tenant") is False


@pytest.mark.asyncio
async def test_get_connection_weight(kb):
    """_get_connection_weight возвращает weight для существующей связи, None для отсутствующей."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    assert await kb._get_connection_weight(id1, id2, "t1") is None
    await kb.link_artifacts(id1, id2, "t1")
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert w == 0.5
    assert await kb._get_connection_weight("x", "y", "t1") is None


@pytest.mark.asyncio
async def test_get_relationships_for_graph(kb):
    """get_relationships_for_graph возвращает связи с weight для визуализации графа."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    id3 = await kb.write_artifact("c", "code", "s3", "t1")
    await kb.link_artifacts(id1, id2, "t1")
    await kb.strengthen_connection(id1, id2, 0.5, "t1")
    await kb.link_artifacts(id2, id3, "t1")
    rels = await kb.get_relationships_for_graph(tenant_id="t1", limit=100)
    assert len(rels) >= 2
    by_edge = {(r["source_id"], r["target_id"]): r["weight"] for r in rels}
    assert (id1, id2) in by_edge
    assert (id2, id3) in by_edge
    assert 0.0 <= by_edge[(id1, id2)] <= 1.0
    rels_all = await kb.get_relationships_for_graph(tenant_id=None, limit=10)
    assert len(rels_all) <= 10


@pytest.mark.asyncio
async def test_strengthen_connection_updates_existing(kb):
    """strengthen_connection обновляет вес существующей связи."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    await kb.link_artifacts(id1, id2, "t1")
    await kb.strengthen_connection(id1, id2, 3.0, "t1")
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert abs(w - 0.8) < 0.001  # 0.5 + 0.1*3 = 0.8


@pytest.mark.asyncio
async def test_strengthen_connection_caps_at_one(kb):
    """strengthen_connection ограничивает вес максимумом 1.0."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    await kb.link_artifacts(id1, id2, "t1")
    await kb.strengthen_connection(id1, id2, 3.0, "t1")  # 0.5 -> 0.8
    await kb.strengthen_connection(id1, id2, 5.0, "t1")  # 0.8 + 0.5 = 1.3 -> 1.0
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert abs(w - 1.0) < 0.001


@pytest.mark.asyncio
async def test_strengthen_connection_raises_artifact_not_found(kb):
    """strengthen_connection поднимает ArtifactNotFoundError при отсутствующем артефакте."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    with pytest.raises(ArtifactNotFoundError, match="Artifact not found: non-existent"):
        await kb.strengthen_connection(id1, "non-existent", 2.0, "t1")
    with pytest.raises(ArtifactNotFoundError, match="Artifact not found: non-existent"):
        await kb.strengthen_connection("non-existent", id1, 2.0, "t1")


@pytest.mark.asyncio
async def test_strengthen_connection_creates_if_missing(kb):
    """strengthen_connection создаёт связь, если её нет."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    assert await kb._get_connection_weight(id1, id2, "t1") is None
    await kb.strengthen_connection(id1, id2, 2.0, "t1")
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert abs(w - 0.7) < 0.001  # min(1.0, 0.5 + 0.2) = 0.7


@pytest.mark.asyncio
async def test_weaken_connection_reduces_weight(kb):
    """weaken_connection уменьшает вес связи."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    await kb.link_artifacts(id1, id2, "t1")
    await kb.strengthen_connection(id1, id2, 3.0, "t1")  # 0.5 -> 0.8
    await kb.weaken_connection(id1, 3.0, "t1")  # 0.8 - 0.3 = 0.5
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert abs(w - 0.5) < 0.001


@pytest.mark.asyncio
async def test_weaken_connection_floors_at_zero(kb):
    """weaken_connection ограничивает вес минимумом 0.0."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    id2 = await kb.write_artifact("b", "code", "s2", "t1")
    await kb.link_artifacts(id1, id2, "t1")  # weight 0.5
    await kb.weaken_connection(id1, 5.0, "t1")  # 0.5 - 0.5 = 0.0
    w = await kb._get_connection_weight(id1, id2, "t1")
    assert abs(w - 0.0) < 0.001


@pytest.mark.asyncio
async def test_weaken_connection_affects_both_directions(kb):
    """weaken_connection ослабляет все связи артефакта (как source и как target)."""
    id_a = await kb.write_artifact("a", "code", "s1", "t1")
    id_b = await kb.write_artifact("b", "code", "s2", "t1")
    id_c = await kb.write_artifact("c", "code", "s3", "t1")
    await kb.link_artifacts(id_a, id_b, "t1")
    await kb.link_artifacts(id_a, id_c, "t1")
    await kb.strengthen_connection(id_a, id_b, 2.0, "t1")  # A->B: 0.7
    await kb.strengthen_connection(id_a, id_c, 2.0, "t1")  # A->C: 0.7
    await kb.weaken_connection(id_a, 3.0, "t1")  # обе связи -0.3
    w_ab = await kb._get_connection_weight(id_a, id_b, "t1")
    w_ac = await kb._get_connection_weight(id_a, id_c, "t1")
    assert abs(w_ab - 0.4) < 0.001
    assert abs(w_ac - 0.4) < 0.001


@pytest.mark.asyncio
async def test_strengthen_connections_batch(kb):
    """strengthen_connections_batch обновляет веса связей пакетно."""
    id_a = await kb.write_artifact("a", "code", "s1", "t1")
    id_b = await kb.write_artifact("b", "code", "s2", "t1")
    id_c = await kb.write_artifact("c", "code", "s3", "t1")
    await kb.link_artifacts(id_a, id_b, "t1")
    await kb.link_artifacts(id_a, id_c, "t1")

    await kb.strengthen_connections_batch(
        [
            {"source_id": id_a, "target_id": id_b, "score": 3.0},
            {"source_id": id_a, "target_id": id_c, "score": 2.0},
        ],
        "t1",
    )

    w_ab = await kb._get_connection_weight(id_a, id_b, "t1")
    w_ac = await kb._get_connection_weight(id_a, id_c, "t1")
    assert abs(w_ab - 0.8) < 0.001  # 0.5 + 0.3
    assert abs(w_ac - 0.7) < 0.001  # 0.5 + 0.2


@pytest.mark.asyncio
async def test_strengthen_connections_batch_creates_new_connections(kb):
    """strengthen_connections_batch создаёт новые связи, если их нет."""
    id_a = await kb.write_artifact("a", "code", "s1", "t1")
    id_b = await kb.write_artifact("b", "code", "s2", "t1")

    await kb.strengthen_connections_batch(
        [{"source_id": id_a, "target_id": id_b, "score": 2.0}],
        "t1",
    )
    w = await kb._get_connection_weight(id_a, id_b, "t1")
    assert abs(w - 0.7) < 0.001  # min(1.0, 0.5 + 0.2)


@pytest.mark.asyncio
async def test_strengthen_connections_batch_raises_artifact_not_found(kb):
    """strengthen_connections_batch поднимает ArtifactNotFoundError при отсутствующем артефакте."""
    id1 = await kb.write_artifact("a", "code", "s1", "t1")
    with pytest.raises(ArtifactNotFoundError, match="Artifact not found: non-existent"):
        await kb.strengthen_connections_batch(
            [{"source_id": id1, "target_id": "non-existent", "score": 1.0}],
            "t1",
        )


@pytest.mark.asyncio
async def test_weaken_connections_batch(kb):
    """weaken_connections_batch ослабляет связи пакетно."""
    id_a = await kb.write_artifact("a", "code", "s1", "t1")
    id_b = await kb.write_artifact("b", "code", "s2", "t1")
    id_c = await kb.write_artifact("c", "code", "s3", "t1")
    await kb.link_artifacts(id_a, id_b, "t1")
    await kb.link_artifacts(id_a, id_c, "t1")
    await kb.strengthen_connection(id_a, id_b, 3.0, "t1")  # 0.8
    await kb.strengthen_connection(id_a, id_c, 3.0, "t1")  # 0.8

    await kb.weaken_connections_batch(
        [
            {"artifact_id": id_a, "penalty": 3.0},
        ],
        "t1",
    )
    w_ab = await kb._get_connection_weight(id_a, id_b, "t1")
    w_ac = await kb._get_connection_weight(id_a, id_c, "t1")
    assert abs(w_ab - 0.5) < 0.001  # 0.8 - 0.3
    assert abs(w_ac - 0.5) < 0.001


@pytest.mark.asyncio
async def test_weaken_connections_batch_empty_ok(kb):
    """weaken_connections_batch с пустым списком — no-op."""
    await kb.weaken_connections_batch([], "t1")


def test_artifact_record_schema():
    """ArtifactRecord валидируется Pydantic."""
    rec = ArtifactRecord(
        id="r1",
        artifact_type="document",
        content="doc content",
    )
    assert rec.id == "r1"
    assert rec.artifact_type == "document"
    assert rec.content == "doc content"
    assert rec.metadata == {}
    assert rec.task_id is None
    assert rec.created_at is not None
