"""Тесты SharedBlackboard (Redis + in-memory)."""
import pytest

from vagus.layer2.communication.blackboard import SharedBlackboard


def _redis_available() -> bool:
    """Проверка доступности Redis на localhost:6379."""
    try:
        import redis
        client = redis.Redis.from_url("redis://localhost:6379/1", decode_responses=True)
        client.ping()
        return True
    except Exception:
        return False


@pytest.fixture(params=[
    pytest.param("memory", id="memory"),
    pytest.param("redis", id="redis", marks=pytest.mark.skipif(
        not _redis_available(), reason="Redis not available"
    )),
])
def blackboard(request):
    """SharedBlackboard с memory или redis backend."""
    backend = request.param
    if backend == "memory":
        return SharedBlackboard(redis_url=None)
    return SharedBlackboard(redis_url="redis://localhost:6379/1")


@pytest.mark.asyncio
async def test_write_read_roundtrip(blackboard):
    """write -> read сохраняет и восстанавливает значение."""
    await blackboard.write("task1", "key1", "plain string")
    assert await blackboard.read("task1", "key1") == "plain string"

    await blackboard.write("task1", "key2", {"a": 1, "b": [2, 3]})
    assert await blackboard.read("task1", "key2") == {"a": 1, "b": [2, 3]}

    await blackboard.write("task1", "key3", 42)
    assert await blackboard.read("task1", "key3") == 42

    await blackboard.write("task1", "key4", [1, 2, "x"])
    assert await blackboard.read("task1", "key4") == [1, 2, "x"]


@pytest.mark.asyncio
async def test_read_nonexistent_key(blackboard):
    """read по отсутствующему ключу возвращает None."""
    assert await blackboard.read("task_unknown", "missing") is None
    await blackboard.write("task2", "exists", "value")
    assert await blackboard.read("task2", "missing") is None


@pytest.mark.asyncio
async def test_read_all_empty(blackboard):
    """read_all для пустой задачи возвращает {}."""
    assert await blackboard.read_all("task_empty") == {}


@pytest.mark.asyncio
async def test_read_all_returns_all(blackboard):
    """read_all возвращает все артефакты задачи."""
    await blackboard.write("task3", "a", 1)
    await blackboard.write("task3", "b", "two")
    await blackboard.write("task3", "c", {"nested": True})
    result = await blackboard.read_all("task3")
    assert result == {"a": 1, "b": "two", "c": {"nested": True}}


@pytest.mark.asyncio
async def test_clear_removes_artifacts(blackboard):
    """clear удаляет все артефакты задачи."""
    await blackboard.write("task4", "k1", "v1")
    await blackboard.write("task4", "k2", "v2")
    assert await blackboard.read_all("task4") == {"k1": "v1", "k2": "v2"}

    await blackboard.clear("task4")
    assert await blackboard.read_all("task4") == {}
    assert await blackboard.read("task4", "k1") is None


@pytest.mark.asyncio
async def test_json_serialization(blackboard):
    """Сериализация/десериализация JSON для вложенных структур."""
    data = {
        "level1": {"level2": [1, 2, {"x": "y"}]},
        "unicode": "Привет мир",
        "numbers": [1.5, 2.7, 3],
    }
    await blackboard.write("task5", "complex", data)
    restored = await blackboard.read("task5", "complex")
    assert restored == data


@pytest.mark.asyncio
async def test_multiple_tasks_isolated(blackboard):
    """Артефакты разных task_id изолированы."""
    await blackboard.write("task_a", "key", "value_a")
    await blackboard.write("task_b", "key", "value_b")
    await blackboard.write("task_c", "other", 999)

    assert await blackboard.read("task_a", "key") == "value_a"
    assert await blackboard.read("task_b", "key") == "value_b"
    assert await blackboard.read("task_c", "other") == 999
    assert await blackboard.read("task_a", "other") is None

    await blackboard.clear("task_b")
    assert await blackboard.read("task_a", "key") == "value_a"
    assert await blackboard.read("task_b", "key") is None
