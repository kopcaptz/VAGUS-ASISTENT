"""
Функциональное тестирование Vagus Assistant - Layer 1.
Запуск: PYTHONPATH=src python scripts/test_functional.py
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_imports():
    """1. БАЗОВАЯ РАБОТОСПОСОБНОСТЬ - Импорты"""
    print("=== 1. ИМПОРТЫ ===")
    try:
        from vagus import (
            LLMRouter, BaseProvider, ConfigManager, AppConfig,
            CacheService, BudgetingService, MonitoringService,
            CircuitBreaker, FallbackHandler,
        )
        print("OK: vagus - все основные импорты")
        return True
    except Exception as e:
        print(f"FAIL: vagus imports: {e}")
        return False


def test_config():
    """Загрузка конфигурации"""
    print("\n=== 2. КОНФИГУРАЦИЯ ===")
    try:
        from vagus.layer0.config import ConfigManager
        from pathlib import Path
        config_path = Path("configs/vagus.yaml")
        if not config_path.exists():
            print("WARN: vagus.yaml не найден (используйте configs/vagus.yaml.example)")
            return True  # не критично
        cm = ConfigManager(config_path=str(config_path), enable_hot_reload=False)
        config = cm.get_config()
        print("OK: Конфигурация загружена")
        return True
    except FileNotFoundError:
        print("WARN: vagus.yaml не найден")
        return True
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_component_init():
    """Инициализация компонентов Layer 1"""
    print("\n=== 3. ИНИЦИАЛИЗАЦИЯ КОМПОНЕНТОВ ===")
    results = []
    try:
        from vagus.layer1.cache import CacheService
        cache = CacheService()
        print("OK: CacheService")
        results.append(True)
    except Exception as e:
        print(f"FAIL: CacheService: {e}")
        results.append(False)

    try:
        from vagus.layer1.budgeting import BudgetingService
        bs = BudgetingService()
        print("OK: BudgetingService")
        results.append(True)
    except Exception as e:
        print(f"FAIL: BudgetingService: {e}")
        results.append(False)

    try:
        from vagus.layer1.monitoring import MonitoringService
        ms = MonitoringService()
        print("OK: MonitoringService")
        results.append(True)
    except Exception as e:
        print(f"FAIL: MonitoringService: {e}")
        results.append(False)

    try:
        from vagus.layer1.fallback import CircuitBreaker, FallbackHandler
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        print("OK: CircuitBreaker")
        results.append(True)
    except Exception as e:
        print(f"FAIL: CircuitBreaker: {e}")
        results.append(False)

    return all(results)


async def test_router_init():
    """Инициализация LLMRouter (без реальных API)"""
    print("\n=== 4. LLM ROUTER (инициализация) ===")
    try:
        from vagus.layer1 import LLMRouter
        router = LLMRouter(
            enable_cache=True,
            enable_budgeting=True,
            enable_monitoring=True,
            fallback_chain=["openai", "anthropic", "deepseek"],
        )
        await router.initialize()
        print("OK: LLMRouter инициализирован")
        print("   Providers:", list(router._providers.keys()))
        stats = router.get_stats()
        print("   Stats:", stats)
        return True
    except Exception as e:
        print(f"FAIL: LLMRouter: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("VAGUS ASSISTANT - ФУНКЦИОНАЛЬНОЕ ТЕСТИРОВАНИЕ\n")
    ok = True
    ok &= test_imports()
    ok &= test_config()
    ok &= test_component_init()
    ok &= asyncio.run(test_router_init())

    print("\n" + "=" * 50)
    if ok:
        print("РЕЗУЛЬТАТ: Все проверки пройдены.")
    else:
        print("РЕЗУЛЬТАТ: Есть ошибки.")
        sys.exit(1)


if __name__ == "__main__":
    main()
