"""Tests for plugin core models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vagus.plugins.core.models import (
    HookDefinition,
    PluginLifecycleState,
    PluginManifest,
    PluginState,
)


def _manifest_payload() -> dict:
    return {
        "name": "demo_plugin",
        "version": "1.2.3",
        "author": "Unit Test",
        "description": "Demo plugin for tests",
        "dependencies": ["pytest>=7.0"],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": "plugin:DemoPlugin",
        "hooks": [
            {
                "name": "on_message_received",
                "priority": 70,
                "callback": "DemoPlugin.on_message_received",
                "is_async": False,
            }
        ],
        "permissions": ["messages:read"],
    }


def test_plugin_manifest_validation_success():
    manifest = PluginManifest(**_manifest_payload())
    assert manifest.name == "demo_plugin"
    assert manifest.version == "1.2.3"
    assert manifest.hooks[0].name == "on_message_received"


def test_plugin_manifest_rejects_non_semver_version():
    payload = _manifest_payload()
    payload["version"] = "1.2"

    with pytest.raises(ValidationError):
        PluginManifest(**payload)


def test_plugin_manifest_rejects_invalid_entry_point():
    payload = _manifest_payload()
    payload["entry_point"] = "not valid entry point"

    with pytest.raises(ValidationError):
        PluginManifest(**payload)


def test_hook_definition_autodetects_async_callback():
    async def callback(_: dict) -> dict:
        return {"ok": True}

    hook = HookDefinition(name="on_message_received", priority=10, callback=callback)
    assert hook.is_async is True


def test_plugin_state_defaults():
    state = PluginState()
    assert state.state == PluginLifecycleState.DISABLED
    assert state.load_time is None
    assert state.error_message is None
