"""
Базовый пример использования LLMRouter.
Запуск: PYTHONPATH=src python examples/layer1/basic_usage.py
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from vagus.layer1 import LLMRouter


async def main():
    router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        enable_monitoring=True,
        fallback_chain=["openai", "anthropic", "deepseek"],
    )
    await router.initialize()
    print("Router initialized. Providers:", list(router._providers.keys()))
    # Без API ключей запрос завершится ошибкой, но инициализация должна пройти
    stats = router.get_stats()
    print("Stats:", stats)


if __name__ == "__main__":
    asyncio.run(main())
