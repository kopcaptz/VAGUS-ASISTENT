"""
Тесты пакетной обработки strengthen_connections_batch с 50 событиями.
Бенчмарк batch vs одиночные запросы, рекомендации по буферизации.

Рекомендация по буферизации:
- 50 событий: при высокой нагрузке quality_gate.passed; batch даёт выигрыш при ≥10–20 событиях
- 100 мс: при низкой нагрузке, чтобы не ждать накопления 50 событий
- Гибрид: flush при count >= 50 ИЛИ time_since_first >= 100ms — оптимально для смешанной нагрузки
"""
import time

import pytest

from vagus.layer2.memory import ArtifactKnowledgeBase


@pytest.fixture
def kb():
    """ArtifactKnowledgeBase с in-memory БД."""
    return ArtifactKnowledgeBase(db_path=":memory:")


@pytest.mark.asyncio
async def test_strengthen_connections_batch_50_events(kb):
    """
    strengthen_connections_batch с 50 событиями: создаём 51 артефакт,
    50 пар (source->target), проверяем корректность весов.
    """
    tenant_id = "t1"

    # Создаём 51 артефакт для 50 связей: (0,1), (1,2), ..., (49,50)
    artifact_ids = []
    for i in range(51):
        aid = await kb.write_artifact(f"content_{i}", "code", f"source_{i}", tenant_id)
        artifact_ids.append(aid)

    updates = [
        {"source_id": artifact_ids[i], "target_id": artifact_ids[i + 1], "score": 1.0}
        for i in range(50)
    ]

    await kb.strengthen_connections_batch(updates, tenant_id)

    # Первая связь (0->1): нет предыдущего веса -> 0.5 + 0.1 = 0.6
    w_first = await kb._get_connection_weight(artifact_ids[0], artifact_ids[1], tenant_id)
    assert abs(w_first - 0.6) < 0.001

    # Середина: например (25->26)
    w_mid = await kb._get_connection_weight(artifact_ids[25], artifact_ids[26], tenant_id)
    assert abs(w_mid - 0.6) < 0.001

    # Последняя связь (49->50)
    w_last = await kb._get_connection_weight(artifact_ids[49], artifact_ids[50], tenant_id)
    assert abs(w_last - 0.6) < 0.001


@pytest.mark.asyncio
async def test_strengthen_connections_batch_vs_single_performance(kb):
    """
    Бенчмарк: batch (50 элементов) vs 50 одиночных strengthen_connection.
    batch_time должен быть существенно меньше single_time.
    """
    tenant_id = "t1"
    artifact_ids = []
    for i in range(51):
        aid = await kb.write_artifact(f"c_{i}", "code", f"s_{i}", tenant_id)
        artifact_ids.append(aid)

    updates = [
        {"source_id": artifact_ids[i], "target_id": artifact_ids[i + 1], "score": 1.0}
        for i in range(50)
    ]

    # Batch: один вызов с 50 элементами
    start = time.perf_counter()
    await kb.strengthen_connections_batch(updates, tenant_id)
    batch_time = time.perf_counter() - start

    # Создаём новый kb для честного сравнения (single на чистой БД)
    kb2 = ArtifactKnowledgeBase(db_path=":memory:")
    artifact_ids2 = []
    for i in range(51):
        aid = await kb2.write_artifact(f"c2_{i}", "code", f"s2_{i}", tenant_id)
        artifact_ids2.append(aid)

    updates2 = [
        {"source_id": artifact_ids2[i], "target_id": artifact_ids2[i + 1], "score": 1.0}
        for i in range(50)
    ]

    # Single: 50 вызовов strengthen_connection
    start = time.perf_counter()
    for u in updates2:
        await kb2.strengthen_connection(u["source_id"], u["target_id"], u["score"], tenant_id)
    single_time = time.perf_counter() - start

    # batch должен быть быстрее (хотя бы в 2 раза при 50 элементах)
    assert batch_time < single_time * 0.5, (
        f"Batch {batch_time:.4f}s should be < 0.5 * single {single_time:.4f}s"
    )
