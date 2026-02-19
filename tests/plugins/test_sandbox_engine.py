"""Tests for sandbox execution engine."""

from __future__ import annotations

import asyncio
from pathlib import Path
import socket
import subprocess

import pytest

from vagus.plugins.core.models import PermissionLevel, PluginPermissions
from vagus.plugins.sandbox.sandbox_engine import SandboxEngine, SandboxExecutionError, SandboxPolicy
from vagus.plugins.sandbox.security_manager import SecurityViolationError


@pytest.mark.asyncio
async def test_sandbox_engine_enforces_timeout():
    engine = SandboxEngine(policy=SandboxPolicy(timeout_seconds=1))
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        filesystem={"read": ["/tmp"], "write": []},
        max_execution_time_seconds=1,
    )

    async def slow_task() -> str:
        await asyncio.sleep(2)
        return "done"

    with pytest.raises(SandboxExecutionError):
        await engine.execute_async("slow_plugin", slow_task, permissions=permissions)


@pytest.mark.asyncio
async def test_sandbox_engine_blocks_process_creation():
    engine = SandboxEngine(policy=SandboxPolicy(timeout_seconds=5))
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        filesystem={"read": ["/tmp"], "write": []},
    )

    def run_process():
        subprocess.run(["echo", "hello"], check=False)

    with pytest.raises(SecurityViolationError):
        await engine.execute_async("proc_plugin", run_process, permissions=permissions)


@pytest.mark.asyncio
async def test_sandbox_engine_filesystem_whitelist(tmp_path: Path):
    allowed = tmp_path / "allowed"
    denied = tmp_path / "denied"
    allowed.mkdir()
    denied.mkdir()
    (allowed / "ok.txt").write_text("ok", encoding="utf-8")
    (denied / "no.txt").write_text("no", encoding="utf-8")

    policy = SandboxPolicy(filesystem_whitelist=[str(allowed)], timeout_seconds=5)
    engine = SandboxEngine(policy=policy)
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        filesystem={"read": [str(allowed), str(denied)], "write": []},
    )

    def read_allowed() -> str:
        with open(allowed / "ok.txt", "r", encoding="utf-8") as fh:
            return fh.read()

    def read_denied() -> str:
        with open(denied / "no.txt", "r", encoding="utf-8") as fh:
            return fh.read()

    result = await engine.execute_async("fs_plugin", read_allowed, permissions=permissions)
    assert result == "ok"

    with pytest.raises(SecurityViolationError):
        await engine.execute_async("fs_plugin", read_denied, permissions=permissions)


@pytest.mark.asyncio
async def test_sandbox_engine_network_whitelist_blocks_domain():
    policy = SandboxPolicy(network_whitelist=["api.openai.com"], timeout_seconds=5)
    engine = SandboxEngine(policy=policy)
    permissions = PluginPermissions(
        level=PermissionLevel.NETWORK,
        network=["api.openai.com", "example.com"],
    )

    def resolve_disallowed() -> None:
        socket.getaddrinfo("example.com", 443)

    with pytest.raises(SecurityViolationError):
        await engine.execute_async("net_plugin", resolve_disallowed, permissions=permissions)


@pytest.mark.asyncio
async def test_sandbox_engine_applies_memory_limit(monkeypatch: pytest.MonkeyPatch):
    from vagus.plugins.sandbox import sandbox_engine

    calls: list[tuple[int, tuple[int, int]]] = []

    class FakeResource:
        RLIMIT_AS = 1
        RLIM_INFINITY = -1

        @staticmethod
        def getrlimit(_limit):
            return (10_000_000_000, 10_000_000_000)

        @staticmethod
        def setrlimit(limit, value):
            calls.append((limit, value))

    monkeypatch.setattr(sandbox_engine, "_RESOURCE_AVAILABLE", True)
    monkeypatch.setattr(sandbox_engine, "resource", FakeResource)

    engine = SandboxEngine(policy=SandboxPolicy(memory_limit_mb=64, timeout_seconds=5))
    permissions = PluginPermissions(level=PermissionLevel.NONE, max_memory_mb=32)

    result = await engine.execute_async("memory_plugin", lambda: "ok", permissions=permissions)
    assert result == "ok"
    assert calls, "Expected setrlimit to be called"
