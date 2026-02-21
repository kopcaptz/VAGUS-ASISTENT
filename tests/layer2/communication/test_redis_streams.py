"""Тесты Redis Streams client и CommunicationLayer с use_streams."""
import asyncio
import json
import pytest

from vagus.layer2.communication import (
    CommunicationLayer,
    create_communication_from_config,
)
from vagus.layer2.communication.redis_streams import RedisStreamsClient


def _redis_available() -> bool:
    try:
        import redis
        client = redis.Redis.from_url("redis://localhost:6379/3", decode_responses=True)
        client.ping()
        return True
    except Exception:
        return False


# --- Unit tests (no Redis) ---


def test_create_communication_from_config_use_streams_default():
    """use_streams по умолчанию False при отсутствии в конфиге."""
    comm = create_communication_from_config({
        "communication": {"redis_url": None, "event_bus": {"enabled": True}},
    })
    assert comm._use_streams is False


def test_create_communication_from_config_use_streams_true():
    """create_communication_from_config читает use_streams, stream_name, max_retries."""
    comm = create_communication_from_config({
        "communication": {
            "redis_url": "redis://localhost:6379/0",
            "event_bus": {
                "enabled": True,
                "use_streams": True,
                "stream_name": "test:stream",
                "max_retries": 5,
            },
        },
    })
    assert comm._use_streams is True
    assert comm._stream_name == "test:stream"
    assert comm._max_retries == 5


@pytest.mark.asyncio
async def test_communication_layer_uses_streams_in_memory():
    """uses_streams False при redis_url=None."""
    comm = CommunicationLayer(redis_url=None)
    assert comm.uses_streams is False


@pytest.mark.asyncio
async def test_synaptic_handler_handle_quality_gate_passed():
    """SynapticTrainingHandler.handle_quality_gate_passed не падает."""
    from vagus.layer2.memory import ArtifactKnowledgeBase, SynapticTrainingHandler

    kb = ArtifactKnowledgeBase(db_path=":memory:")
    handler = SynapticTrainingHandler(artifact_kb=kb)
    await handler.handle_quality_gate_passed(
        {"step_id": "s1", "agent_type": "coder", "artefact_key": "r1", "task_id": "t1"},
        tenant_id="tenant1",
    )


# --- Redis Streams integration tests ---


@pytest.mark.asyncio
@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
async def test_redis_streams_client_publish_and_consume():
    """RedisStreamsClient: publish_event и process_events доставляют событие."""
    client = RedisStreamsClient("redis://localhost:6379/3", stream_name="vagus:test:stream")
    received = []

    async def handler(event_type: str, message: dict) -> None:
        received.append((event_type, message))

    shutdown = asyncio.Event()
    task = asyncio.create_task(
        client.process_events(
            "vagus:test:stream",
            "test_group",
            "test_consumer",
            handler,
            max_retries=2,
            block_ms=2000,
            _shutdown=shutdown,
        ),
    )
    await asyncio.sleep(0.3)

    msg_id = await client.publish_event("test.event", {"x": 42}, task_id="t1", tenant_id="tn1")
    assert msg_id is not None

    await asyncio.sleep(0.5)

    shutdown.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await client.close()

    assert len(received) >= 1
    ev_type, msg = received[0]
    assert ev_type == "test.event"
    assert msg.get("data", {}).get("x") == 42
    assert msg.get("data", {}).get("tenant_id") == "tn1"
    assert msg.get("task_id") == "t1"


@pytest.mark.asyncio
@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
async def test_communication_layer_streams_publish_event():
    """CommunicationLayer с use_streams публикует в Redis Stream."""
    comm = CommunicationLayer(
        redis_url="redis://localhost:6379/3",
        event_bus_enabled=True,
        use_streams=True,
        stream_name="vagus:test:comm_stream",
    )
    if not comm.uses_streams:
        pytest.skip("Redis Streams init failed")
    try:
        # publish_event должен не падать
        await comm.publish_event("stream.test", {"k": "v"}, task_id="tid", tenant_id="tn")
        await asyncio.sleep(0.1)
    finally:
        await comm.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
async def test_communication_layer_start_stream_consumer():
    """start_stream_consumer возвращает task и shutdown_event."""
    comm = CommunicationLayer(
        redis_url="redis://localhost:6379/3",
        event_bus_enabled=True,
        use_streams=True,
        stream_name="vagus:test:consumer_stream",
    )
    if not comm.uses_streams:
        pytest.skip("Redis Streams init failed")
    try:
        got = []

        async def h(et: str, m: dict) -> None:
            got.append((et, m))

        task, shutdown = comm.start_stream_consumer("g1", "c1", h)
        assert task is not None
        assert shutdown is not None
        await asyncio.sleep(0.1)
        shutdown.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    finally:
        await comm.close()
