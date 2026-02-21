"""
Инфраструктурные тесты Redis Streams.
Проверяют: подключение, версию Redis, publish/read, consumer groups.
Используется redis://localhost:6379/4 для изоляции от других тестов.
"""
import pytest

REDIS_URL = "redis://localhost:6379/4"
INFRA_STREAM = "vagus:infra:test:stream"


def _redis_available() -> bool:
    try:
        import redis
        r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_redis_connection():
    """redis.ping() == True — Redis доступен."""
    import redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    assert r.ping() is True


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_redis_version():
    """Redis server version >= 7.0 для Streams."""
    import redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    info = r.info("server")
    version_str = info.get("redis_version", "0")
    major = int(version_str.split(".")[0])
    assert major >= 7, f"Redis {version_str} < 7.0 required for Streams"


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_stream_publish_read():
    """XADD -> XRANGE: сообщение доставлено в stream."""
    import redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    stream = f"{INFRA_STREAM}:pubread"
    msg_id = r.xadd(stream, {"event": "test", "data": "hello"}, id="*", maxlen=100)
    assert msg_id

    entries = r.xrange(stream)
    assert len(entries) >= 1
    eid, fields = entries[0]
    assert eid == msg_id
    assert fields.get("event") == "test"
    assert fields.get("data") == "hello"

    r.delete(stream)


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_consumer_group_create():
    """XGROUP CREATE — consumer group создаётся."""
    import redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    stream = f"{INFRA_STREAM}:group"
    r.xadd(stream, {"init": "1"}, id="*", maxlen=10)

    try:
        r.xgroup_create(stream, "infra_test_group", id="$", mkstream=True)
        created = True
    except Exception as e:
        if "BUSYGROUP" in str(e) or "already exists" in str(e).lower():
            created = True
        else:
            raise

    assert created
    r.delete(stream)


@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
def test_consumer_group_read():
    """XREADGROUP — чтение из consumer group."""
    import redis
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)

    stream = f"{INFRA_STREAM}:read"
    r.xadd(stream, {"init": "1"}, id="*", maxlen=10)

    try:
        r.xgroup_create(stream, "infra_read_group", id="$", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" not in str(e) and "already exists" not in str(e).lower():
            raise

    r.xadd(stream, {"event": "cg_test", "payload": "42"}, id="*", maxlen=10)

    msgs = r.xreadgroup(
        groupname="infra_read_group",
        consumername="infra_consumer",
        streams={stream: ">"},
        count=5,
        block=1000,
    )

    assert msgs
    stream_name, entries = msgs[0]
    assert len(entries) >= 1
    msg_id, fields = entries[0]
    assert fields.get("event") == "cg_test"

    r.xack(stream, "infra_read_group", msg_id)
    r.delete(stream)
