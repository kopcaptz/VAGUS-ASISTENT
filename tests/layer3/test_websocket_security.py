"""Unit-тесты для websocket_security utilities."""

from types import SimpleNamespace

from vagus.layer3.api.websocket_security import (
    WebSocketAuditStorage,
    WebSocketRuntimeSettings,
    create_runtime_settings_from_config,
)


def test_runtime_settings_max_message_size_bytes():
    settings = WebSocketRuntimeSettings(max_message_size_mb=10)
    assert settings.max_message_size_bytes == 10 * 1024 * 1024


def test_create_runtime_settings_from_none_uses_defaults():
    settings = create_runtime_settings_from_config(None)
    assert settings.max_message_size_mb == 10
    assert settings.ping_interval_seconds == 30
    assert settings.ping_timeout_seconds == 60
    assert settings.max_messages_per_minute == 100


def test_create_runtime_settings_without_websocket_uses_defaults():
    config = SimpleNamespace()
    settings = create_runtime_settings_from_config(config)
    assert settings.max_message_size_mb == 10
    assert settings.ping_interval_seconds == 30
    assert settings.ping_timeout_seconds == 60


def test_create_runtime_settings_from_config_overrides_values():
    websocket_cfg = SimpleNamespace(
        max_message_size_mb=20,
        ping_interval_seconds=15,
        ping_timeout_seconds=45,
        max_messages_per_minute=250,
    )
    config = SimpleNamespace(websocket=websocket_cfg)
    settings = create_runtime_settings_from_config(config)

    assert settings.max_message_size_mb == 20
    assert settings.ping_interval_seconds == 15
    assert settings.ping_timeout_seconds == 45
    assert settings.max_messages_per_minute == 250


def test_create_runtime_settings_partial_config_fallbacks():
    websocket_cfg = SimpleNamespace(max_message_size_mb=8)
    config = SimpleNamespace(websocket=websocket_cfg)
    settings = create_runtime_settings_from_config(config)

    assert settings.max_message_size_mb == 8
    assert settings.ping_interval_seconds == 30
    assert settings.ping_timeout_seconds == 60


def test_audit_storage_list_events_empty(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-empty.db"))
    assert storage.list_events() == []


def test_audit_storage_records_and_orders_newest_first(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-order.db"))
    storage.log_event(event_type="connect", user_id="u1", task_id="t1")
    storage.log_event(event_type="close", user_id="u1", task_id="t1", close_code=1000)

    events = storage.list_events(limit=10)
    assert len(events) == 2
    assert events[0]["event_type"] == "close"
    assert events[1]["event_type"] == "connect"


def test_audit_storage_filter_by_task_id(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-task-filter.db"))
    storage.log_event(event_type="connect", user_id="u1", task_id="task-a")
    storage.log_event(event_type="connect", user_id="u1", task_id="task-b")

    events = storage.list_events(task_id="task-a")
    assert len(events) == 1
    assert events[0]["task_id"] == "task-a"


def test_audit_storage_filter_by_user_id(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-user-filter.db"))
    storage.log_event(event_type="connect", user_id="u1", task_id="t1")
    storage.log_event(event_type="connect", user_id="u2", task_id="t1")

    events = storage.list_events(user_id="u2")
    assert len(events) == 1
    assert events[0]["user_id"] == "u2"


def test_audit_storage_filter_by_event_type(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-event-filter.db"))
    storage.log_event(event_type="connect", user_id="u1", task_id="t1")
    storage.log_event(event_type="message_sent", user_id="u1", task_id="t1")

    events = storage.list_events(event_type="message_sent")
    assert len(events) == 1
    assert events[0]["event_type"] == "message_sent"


def test_audit_storage_limit_is_applied(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-limit.db"))
    storage.log_event(event_type="connect", user_id="u1", task_id="t1")
    storage.log_event(event_type="message_sent", user_id="u1", task_id="t1")
    storage.log_event(event_type="close", user_id="u1", task_id="t1")

    events = storage.list_events(limit=2)
    assert len(events) == 2


def test_audit_storage_message_metadata_roundtrip(tmp_path):
    storage = WebSocketAuditStorage(str(tmp_path / "audit-metadata.db"))
    storage.log_event(
        event_type="message_sent",
        user_id="admin",
        task_id="task-1",
        message_size_bytes=128,
        message_type="ping",
        close_code=None,
        reason=None,
        duration_seconds=None,
    )
    events = storage.list_events(limit=1)
    assert events[0]["message_size_bytes"] == 128
    assert events[0]["message_type"] == "ping"
