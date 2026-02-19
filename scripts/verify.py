#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vagus Asistent - verification script.
Run: PYTHONPATH=src python scripts/verify.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    errors = []
    # 1. Imports
    try:
        from vagus.layer1.balancing import CostStrategy, HybridStrategy
        from vagus.layer1.cache import CacheService
        from vagus.layer1.fallback import CircuitBreaker
        print("[OK] Imports")
    except Exception as e:
        errors.append(f"Импорты: {e}")
        print(f"[FAIL] Imports: {e}")
        return 1

    # 2. Стратегия
    try:
        s = CostStrategy()
        r = s.select_provider({"a": {"cost": 0.1}, "b": {"cost": 0.05}}, {})
        assert r == "b"
        print("[OK] CostStrategy")
    except Exception as e:
        errors.append(f"CostStrategy: {e}")
        print(f"[FAIL] CostStrategy: {e}")

    # 3. Кэш
    try:
        import asyncio
        async def _():
            cache = CacheService(ttl_seconds=60, max_size_mb=1)
            await cache.set("test", "ok")
            v = await cache.get("test")
            assert v == "ok"
        asyncio.run(_())
        print("[OK] CacheService")
    except Exception as e:
        errors.append(f"CacheService: {e}")
        print(f"[FAIL] CacheService: {e}")

    # 4. Circuit Breaker
    try:
        import asyncio
        async def _():
            cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
            async def ok():
                return 42
            r = await cb.call(ok)
            assert r == 42
        asyncio.run(_())
        print("[OK] CircuitBreaker")
    except Exception as e:
        errors.append(f"CircuitBreaker: {e}")
        print(f"[FAIL] CircuitBreaker: {e}")

    if errors:
        print(f"\nErrors: {len(errors)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
