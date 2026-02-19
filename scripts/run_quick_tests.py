"""
Быстрое тестирование без полной загрузки vagus.
Обходит возможные блокировки при импорте (OneDrive, watchdog и т.д.)
"""
import sys
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def main():
    results = []
    
    # 1. CostStrategy - минимальный импорт
    try:
        from vagus.layer1.balancing.cost_strategy import CostStrategy
        s = CostStrategy()
        r = s.select_provider({"a": {"cost": 0.1}, "b": {"cost": 0.05}}, {})
        assert r == "b"
        results.append(("CostStrategy", True, None))
    except Exception as e:
        results.append(("CostStrategy", False, str(e)))
    
    # 2. HybridStrategy
    try:
        from vagus.layer1.balancing.hybrid_strategy import HybridStrategy
        s = HybridStrategy()
        providers = {"a": {"cost": 0.1, "latency": 100, "quality": 0.9}, "b": {"cost": 0.05, "latency": 50, "quality": 0.7}}
        pid = s.select_provider(providers, {"priority": "normal"})
        assert pid in ("a", "b")
        results.append(("HybridStrategy", True, None))
    except Exception as e:
        results.append(("HybridStrategy", False, str(e)))
    
    # 3. LatencyStrategy
    try:
        from vagus.layer1.balancing.latency_strategy import LatencyStrategy
        s = LatencyStrategy()
        r = s.select_provider({"a": {"e2e_ms": 200}, "b": {"e2e_ms": 50}}, {})
        assert r == "b"
        results.append(("LatencyStrategy", True, None))
    except Exception as e:
        results.append(("LatencyStrategy", False, str(e)))
    
    # 4. CacheService
    async def _cache():
        from vagus.layer1.cache.cache_service import CacheService
        cache = CacheService(ttl_seconds=60, max_size_mb=1)
        await cache.set("x", "y")
        v = await cache.get("x")
        assert v == "y"
        return True
    try:
        asyncio.run(_cache())
        results.append(("CacheService", True, None))
    except Exception as e:
        results.append(("CacheService", False, str(e)))
    
    # 5. CircuitBreaker
    async def _cb():
        from vagus.layer1.fallback.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        async def ok():
            return 42
        r = await cb.call(ok)
        assert r == 42
        return True
    try:
        asyncio.run(_cb())
        results.append(("CircuitBreaker", True, None))
    except Exception as e:
        results.append(("CircuitBreaker", False, str(e)))
    
    # 6. BudgetingService
    async def _budget():
        import tempfile
        from vagus.layer1.budgeting.budgeting_service import BudgetingService
        with tempfile.TemporaryDirectory() as td:
            bs = BudgetingService(daily_limit=1.0, monthly_limit=10.0, data_dir=td)
            await bs.check_budget(0.5)
            return True
    try:
        asyncio.run(_budget())
        results.append(("BudgetingService", True, None))
    except Exception as e:
        results.append(("BudgetingService", False, str(e)))
    
    # Output
    ok_count = sum(1 for _, ok, _ in results if ok)
    for name, ok, err in results:
        status = "OK" if ok else f"FAIL: {err}"
        print(f"  {name}: {status}")
    print(f"\nРезультат: {ok_count}/{len(results)} тестов пройдено")
    return 0 if ok_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
