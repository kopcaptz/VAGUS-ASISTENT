"""Tests for production security hardening policies."""

from __future__ import annotations

import pytest

from vagus.plugins.security import (
    PluginResourceQuota,
    PluginSecurityHardening,
    PluginSecurityHardeningError,
)


def test_security_hardening_requires_signature_in_production():
    hardening = PluginSecurityHardening(production_mode=True, require_signatures=True)
    with pytest.raises(PluginSecurityHardeningError):
        hardening.check_operation("plugin_a", operation="load", signed=False)


def test_security_hardening_allows_signed_operation():
    hardening = PluginSecurityHardening(production_mode=True, require_signatures=True)
    hardening.check_operation("plugin_a", operation="load", signed=True)
    audit = hardening.get_audit_log("plugin_a")
    assert audit and audit[-1].allowed is True


def test_security_hardening_rate_limit_enforced():
    hardening = PluginSecurityHardening(production_mode=False)
    hardening.register_quota("plugin_b", PluginResourceQuota(max_calls_per_minute=1))
    hardening.check_operation("plugin_b", operation="call", signed=False)
    with pytest.raises(PluginSecurityHardeningError):
        hardening.check_operation("plugin_b", operation="call", signed=False)


def test_security_hardening_memory_quota_enforced():
    hardening = PluginSecurityHardening(production_mode=False)
    hardening.register_quota("plugin_c", PluginResourceQuota(max_memory_mb=32.0))
    with pytest.raises(PluginSecurityHardeningError):
        hardening.check_operation(
            "plugin_c",
            operation="run",
            estimated_memory_mb=64.0,
        )


def test_security_hardening_execution_time_quota_enforced():
    hardening = PluginSecurityHardening(production_mode=False)
    hardening.register_quota("plugin_d", PluginResourceQuota(max_execution_time_seconds=1.0))
    with pytest.raises(PluginSecurityHardeningError):
        hardening.check_operation(
            "plugin_d",
            operation="run",
            estimated_execution_time_seconds=5.0,
        )
