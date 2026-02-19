"""Tests for orchestrator scalability helpers."""

import pytest

from vagus.layer2 import CommunicationLayer, TaskOrchestrator


@pytest.mark.asyncio
async def test_orchestrator_shared_queue_in_memory_enqueue_dequeue():
    orchestrator = TaskOrchestrator(
        communication=CommunicationLayer(),
        cluster_config={
            "enabled": True,
            "shared_task_queue": {"enabled": False},
            "distributed_locking": {"enabled": False},
        },
    )
    payload = {"task_id": "q1", "prompt": "hello"}
    await orchestrator.enqueue_task_for_cluster(payload)
    restored = await orchestrator.dequeue_task_for_cluster(timeout_seconds=1.0)
    assert restored == payload


def test_orchestrator_scalability_stats_shape():
    orchestrator = TaskOrchestrator(communication=CommunicationLayer())
    stats = orchestrator.get_scalability_stats()
    assert "cluster_enabled" in stats
    assert "shared_task_queue" in stats
    assert "distributed_locking" in stats
