# Vagus Asistent

Многослойная агентная система с мульти-модельным роутером LLM.

## Возможности

- **Слой 0**: Конфигурация, логирование
- **Слой 1**: Ядро LLM
  - Роутер с балансировкой нагрузки
  - Провайдеры: OpenAI, Anthropic, DeepSeek, OpenRouter, Google
  - Fallback с Circuit Breaker и exponential backoff
  - Кэширование с TTL
  - Бюджетирование (дневные/месячные лимиты)
  - Мониторинг в SQLite
  - Стратегии: cost, latency, quality, hybrid

## Требования

- Python 3.10+
- pip

## Установка

```bash
git clone <repository-url>
cd Vagus_Asistent
pip install -r requirements.txt
```

## Настройка

```bash
cp .env.example .env
# Отредактируйте .env и добавьте API ключи
```

## Использование

```python
import asyncio
from vagus.layer1 import LLMRouter

async def main():
    router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        fallback_chain=["openai", "anthropic", "deepseek"],
    )
    await router.initialize()

    async for chunk in router.route_request(
        prompt="Привет!",
        stream=True,
        priority="normal",
    ):
        print(chunk.get("content", ""), end="")

asyncio.run(main())
```

Запуск примера:

```bash
PYTHONPATH=src python examples/layer1/basic_usage.py
```

## Проверка и тестирование

Быстрая проверка (без API):

```bash
PYTHONPATH=src python scripts/verify.py
```

Тесты:

```bash
PYTHONPATH=src pytest tests/layer1/unit/ -v
```

## Структура проекта

```
Vagus_Asistent/
├── src/vagus/          # Исходный код
│   ├── layer0/         # Конфигурация, логирование
│   └── layer1/         # Роутер LLM
├── tests/
├── docs/
├── examples/
└── configs/
```

## Документация

- [TZ_LAYER1.md](TZ_LAYER1.md) — техническое задание Слоя 1
- [docs/layer1/](docs/layer1/) — API, архитектура, конфигурация

## Лицензия

MIT
