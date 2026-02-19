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

    # 5. Auto performance benchmark (run only on source changes)
    try:
        import asyncio

        from vagus.benchmarking.performance_benchmark import (
            PerformanceBenchmarkRunner,
            auto_run_if_sources_changed,
        )
        from vagus.layer1.monitoring.metrics_storage import MetricsStorage

        async def _run_benchmark_suite():
            runner = PerformanceBenchmarkRunner(output_dir="benchmark_results")
            cache = CacheService(ttl_seconds=60, max_size_mb=1)
            storage = MetricsStorage("metrics.db")
            result = await runner.benchmark_cache_hit_miss(cache_service=cache, iterations=3)
            out = runner.save_results(
                suite_name="verify_quick",
                scenario_results=[result],
                extra={"source": "scripts.verify"},
            )
            return {"result_path": str(out)}

        benchmark_status = asyncio.run(
            auto_run_if_sources_changed(
                source_paths=["src/vagus/layer1", "src/vagus/layer2", "src/vagus/layer3"],
                state_file=".benchmark/verify_state.json",
                benchmark_coro=_run_benchmark_suite,
            )
        )
        if benchmark_status.get("executed"):
            print("[OK] Performance benchmark auto-run (executed)")
        else:
            print("[OK] Performance benchmark auto-run (skipped)")
    except Exception as e:
        errors.append(f"BenchmarkAutoRun: {e}")
        print(f"[FAIL] BenchmarkAutoRun: {e}")

    if errors:
        print(f"\nErrors: {len(errors)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
