# Инструкция по установке и первому запуску

## 1. Установка

```bash
git clone <url-репозитория>
cd Vagus_Asistent
pip install -r requirements.txt
```

## 2. Настройка

Скопируйте файл с примером переменных окружения:

```bash
cp .env.example .env
```

Откройте `.env` и добавьте API ключи провайдеров (хотя бы один):

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
```

## 3. Проверка работоспособности

Быстрая проверка без API-вызовов:

```bash
PYTHONPATH=src python scripts/verify.py
```

Запуск примера:

```bash
PYTHONPATH=src python examples/layer1/basic_usage.py
```

## 4. Тестирование

```bash
PYTHONPATH=src pytest tests/layer1/unit/ -v
```

Или (если pytest.ini настроен):

```bash
pytest tests/layer1/unit/ -v
```

## 5. Использование в коде

```python
import asyncio
from vagus.layer1 import LLMRouter

async def main():
    router = LLMRouter(enable_cache=True, enable_budgeting=True)
    await router.initialize()
    async for chunk in router.route_request("Привет!", stream=True):
        print(chunk.get("content", ""), end="")

asyncio.run(main())
```

## Структура коммита

Перед первым push убедитесь:

1. `.env` в `.gitignore` (не коммитить секреты)
2. Запуск `python scripts/verify.py` завершается успешно
3. Тесты проходят: `pytest tests/layer1/unit/ -v`
