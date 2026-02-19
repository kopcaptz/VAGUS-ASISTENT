#!/usr/bin/env python3
"""
Vagus Asistent — quick verification script.
Checks that all layers can be imported and core components work.

Run:
    PYTHONPATH=src python scripts/verify.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _ok(label: str):
    print(f"  [OK]   {label}")


def _fail(label: str, err):
    print(f"  [FAIL] {label}: {err}")


def main() -> int:
    errors: list[str] = []

    # ── 1. Layer 0 imports ──────────────────────────────────────────
    print("Layer 0 — Config & Logging")
    try:
        from vagus.layer0.config import ConfigManager, AppConfig, Layer1Config
        from vagus.layer0.logging import get_logger
        from vagus.layer0.adapters import config_adapter
        _ok("imports")
    except Exception as e:
        _fail("imports", e)
        errors.append(str(e))

    # ── 2. Layer 1 imports ──────────────────────────────────────────
    print("Layer 1 — LLM Router")
    try:
        from vagus.layer1 import LLMRouter, CacheService, BudgetingService, MonitoringService
        from vagus.layer1.balancing import CostStrategy, HybridStrategy
        from vagus.layer1.fallback import CircuitBreaker, FallbackHandler
        _ok("imports")
    except Exception as e:
        _fail("imports", e)
        errors.append(str(e))

    # ── 3. Layer 2 imports ──────────────────────────────────────────
    print("Layer 2 — Orchestration")
    try:
        from vagus.layer2 import TaskOrchestrator, CommunicationLayer
        from vagus.layer2.agents import ResearcherAgent, CoderAgent, AnalystAgent
        from vagus.layer2.memory import EpisodicMemory, SemanticMemory
        from vagus.layer2.skills import SkillSystem
        _ok("imports")
    except Exception as e:
        _fail("imports", e)
        errors.append(str(e))

    # ── 4. Layer 3 imports ──────────────────────────────────────────
    print("Layer 3 — Interfaces")
    try:
        from vagus.layer3.api.main import app as fastapi_app
        from vagus.layer3.api.models import TaskCreateRequest, TaskStatus
        from vagus.layer3.cli.app import app as cli_app
        from vagus.layer3.channels.gateway import ChannelGateway
        _ok("imports")
    except Exception as e:
        _fail("imports", e)
        errors.append(str(e))

    # ── 5. CostStrategy smoke test ─────────────────────────────────
    print("Smoke tests")
    try:
        s = CostStrategy()
        result = s.select_provider({"a": {"cost": 0.1}, "b": {"cost": 0.05}}, {})
        assert result == "b", f"Expected 'b', got '{result}'"
        _ok("CostStrategy")
    except Exception as e:
        _fail("CostStrategy", e)
        errors.append(str(e))

    # ── 6. CacheService smoke test ──────────────────────────────────
    try:
        import asyncio
        async def _cache_test():
            cache = CacheService(ttl_seconds=60, max_size_mb=1)
            await cache.set("test_key", "test_value")
            v = await cache.get("test_key")
            assert v == "test_value"
        asyncio.run(_cache_test())
        _ok("CacheService")
    except Exception as e:
        _fail("CacheService", e)
        errors.append(str(e))

    # ── 7. CircuitBreaker smoke test ────────────────────────────────
    try:
        import asyncio
        async def _cb_test():
            cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
            async def ok_fn():
                return 42
            r = await cb.call(ok_fn)
            assert r == 42
        asyncio.run(_cb_test())
        _ok("CircuitBreaker")
    except Exception as e:
        _fail("CircuitBreaker", e)
        errors.append(str(e))

    # ── 8. API key check ────────────────────────────────────────────
    print("Environment")
    api_keys = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY"),
    }
    found = [k for k, v in api_keys.items() if v]
    if found:
        _ok(f"API keys found: {', '.join(found)}")
    else:
        print("  [WARN] No API keys in environment (set in .env)")

    # ── Summary ─────────────────────────────────────────────────────
    print()
    if errors:
        print(f"RESULT: {len(errors)} error(s)")
        return 1
    print("RESULT: All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
