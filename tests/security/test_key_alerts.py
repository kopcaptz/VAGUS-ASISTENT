"""Tests for key alert manager behavior."""

from __future__ import annotations

import pytest

from vagus.security import KeyAlertConfig, KeyAlertManager, KeyManager


class _StubAlertingService:
    def __init__(self) -> None:
        self.last_alerts = []

    def notify(self, alerts):
        self.last_alerts = list(alerts)
        return {"sent": len(self.last_alerts), "errors": []}


@pytest.mark.asyncio
async def test_key_alerts_throttling_and_escalation(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    manager = KeyManager()
    manager.add_key(name="openai", key_type="openai", value="sk-test-1234567890", expires_at=None)

    # Force invalid validation metadata for deterministic alerts.
    monkeypatch.setattr(manager, "_validate_online", lambda **_: (False, "invalid"))
    manager.validate_key("openai", online=True)

    service = _StubAlertingService()
    alerts = KeyAlertManager(
        key_manager=manager,
        alerting_service=service,  # type: ignore[arg-type]
        config=KeyAlertConfig(
            enabled=True,
            interval_seconds=60,
            expiring_days_threshold=7,
            throttle_seconds=0,
            escalation_warnings=3,
        ),
    )

    first = await alerts.run_once()
    assert first["sent"] >= 1
    assert any(a.rule == "key_validation_failed" for a in first["alerts"])

    second = await alerts.run_once()
    assert second["sent"] >= 1
    third = await alerts.run_once()
    assert third["sent"] >= 1
    # 3 warnings -> critical escalation.
    escalated = [a for a in third["alerts"] if a.rule == "key_validation_failed"]
    assert escalated
    assert any(a.severity == "critical" for a in escalated)
