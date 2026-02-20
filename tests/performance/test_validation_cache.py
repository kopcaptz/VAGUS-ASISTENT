"""Performance-focused tests for validation cache behavior."""

from __future__ import annotations

import time

from vagus.security import KeyManager


def test_validation_cache_avoids_repeated_online_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    manager = KeyManager()
    manager.add_key(name="openai", key_type="openai", value="sk-test-1234567890")
    manager._validation_min_interval_seconds = 0.0

    calls = {"count": 0}

    def _fake_online(**kwargs):
        calls["count"] += 1
        time.sleep(0.01)
        return True, None

    monkeypatch.setattr(manager, "_validate_online", _fake_online)

    t1 = time.perf_counter()
    ok1, _ = manager.validate_key("openai", online=True)
    d1 = time.perf_counter() - t1
    t2 = time.perf_counter()
    ok2, _ = manager.validate_key("openai", online=True)
    d2 = time.perf_counter() - t2

    assert ok1 is True
    assert ok2 is True
    assert calls["count"] == 1
    assert d2 <= d1

    manager.update_key(name="openai", value="sk-test-updated-1234567890")
    ok3, _ = manager.validate_key("openai", online=True)
    assert ok3 is True
    assert calls["count"] == 2
