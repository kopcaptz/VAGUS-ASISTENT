#!/usr/bin/env python3
"""
Vagus Asistent — functional tests for all layers.
Exercises the real components (without live API calls).

Run:
    PYTHONPATH=src python scripts/test_functional.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _section(title: str):
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print('=' * 50)


def test_imports() -> bool:
    _section("1. IMPORTS — all layers")
    try:
        from vagus import LLMRouter, ConfigManager, CacheService, BudgetingService
        from vagus.layer2 import TaskOrchestrator, create_orchestrator_full
        from vagus.layer3.api.main import app
        print("  OK: all key imports succeed")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_config() -> bool:
    _section("2. CONFIG — ConfigManager + Layer models")
    try:
        from vagus.layer0.config import ConfigManager
        config_path = Path("configs/vagus.yaml")
        if not config_path.exists():
            print("  WARN: configs/vagus.yaml not found (using defaults)")
            return True
        cm = ConfigManager(config_path=str(config_path), enable_hot_reload=False)
        config = cm.load()
        print(f"  OK: config loaded (version={config.version})")
        print(f"      model={config.global_settings.default_model}")
        ttl = cm.get("layer1.cache.ttl_seconds", default="N/A")
        print(f"      layer1.cache.ttl_seconds={ttl}")
        return True
    except FileNotFoundError:
        print("  WARN: vagus.yaml not found")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_layer1_components() -> bool:
    _section("3. LAYER 1 — Component initialisation")
    ok = True
    components = []

    try:
        from vagus.layer1.cache import CacheService
        CacheService(ttl_seconds=60, max_size_mb=1)
        components.append("CacheService")
    except Exception as e:
        print(f"  FAIL CacheService: {e}")
        ok = False

    try:
        from vagus.layer1.budgeting import BudgetingService
        BudgetingService()
        components.append("BudgetingService")
    except Exception as e:
        print(f"  FAIL BudgetingService: {e}")
        ok = False

    try:
        from vagus.layer1.monitoring import MonitoringService
        MonitoringService()
        components.append("MonitoringService")
    except Exception as e:
        print(f"  FAIL MonitoringService: {e}")
        ok = False

    try:
        from vagus.layer1.fallback import CircuitBreaker
        CircuitBreaker("test", failure_threshold=3)
        components.append("CircuitBreaker")
    except Exception as e:
        print(f"  FAIL CircuitBreaker: {e}")
        ok = False

    if ok:
        print(f"  OK: {', '.join(components)}")
    return ok


async def test_router_init() -> bool:
    _section("4. LAYER 1 — LLMRouter initialisation")
    try:
        from vagus.layer1 import LLMRouter
        router = LLMRouter(
            enable_cache=True,
            enable_budgeting=True,
            enable_monitoring=True,
        )
        await router.initialize()
        print(f"  OK: LLMRouter initialised")
        print(f"      providers: {list(router._providers.keys())}")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_layer2_orchestrator() -> bool:
    _section("5. LAYER 2 — TaskOrchestrator")
    try:
        from vagus.layer2 import create_orchestrator_full
        from vagus.layer1 import LLMRouter

        router = LLMRouter(enable_cache=False, enable_budgeting=False, enable_monitoring=False)
        await router.initialize()
        orchestrator = create_orchestrator_full(router)
        print(f"  OK: orchestrator with {len(orchestrator.agents)} agents")
        for a in orchestrator.agents:
            print(f"      - {a.name}: {a.description}")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_layer3_api() -> bool:
    _section("6. LAYER 3 — FastAPI app")
    try:
        from vagus.layer3.api.main import app
        from vagus.layer3.api.models import TaskCreateRequest, TaskStatus

        req = TaskCreateRequest(prompt="test", task_type="default")
        assert req.prompt == "test"
        assert TaskStatus.PENDING == "pending"
        print(f"  OK: FastAPI app + Pydantic models")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def test_adapter() -> bool:
    _section("7. LAYER 0 — Config adapter")
    try:
        from vagus.layer0.adapters import get, get_int, get_bool
        val = get("nonexistent", default="fallback")
        assert val == "fallback"
        assert get_int("x", default=42) == 42
        assert get_bool("x", default=True) is True
        print("  OK: adapter fallback works")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


def main():
    print("VAGUS ASISTENT — FUNCTIONAL TESTS\n")
    ok = True
    ok &= test_imports()
    ok &= test_config()
    ok &= test_layer1_components()
    ok &= asyncio.run(test_router_init())
    ok &= asyncio.run(test_layer2_orchestrator())
    ok &= test_layer3_api()
    ok &= test_adapter()

    print("\n" + "=" * 50)
    if ok:
        print("RESULT: All functional tests passed.")
    else:
        print("RESULT: Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
