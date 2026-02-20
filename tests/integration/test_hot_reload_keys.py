"""Integration tests for key hot-reload watcher."""

from __future__ import annotations

import os
import time

from vagus.security import KeyManager


def test_key_watcher_emits_external_change_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    manager = KeyManager()
    manager.add_key(name="openai", key_type="openai", value="sk-test-1234567890")

    events = []
    manager.add_listener(lambda event: events.append(event))
    manager.watch_for_changes(interval_seconds=1)
    try:
        # Simulate external modification by touching encrypted file.
        os.utime(manager.keys_file, None)
        deadline = time.time() + 8
        while time.time() < deadline:
            if any(item.get("action") == "external_change" for item in events):
                break
            time.sleep(0.25)
        assert any(item.get("action") == "external_change" for item in events)
    finally:
        manager.stop_watching()
