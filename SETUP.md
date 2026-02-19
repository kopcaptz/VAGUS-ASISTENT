# Инструкция по установке и запуску

## 1. Установка

```bash
git clone https://github.com/kopcaptz/VAGUS-ASISTENT.git
cd VAGUS-ASISTENT
pip install -r requirements.txt
```

## 2. Настройка

```bash
cp .env.example .env
```

Добавьте API-ключи провайдеров (хотя бы один):

```
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
VAGUS_SECRET_KEY=your-secret-key-for-jwt
```

## 3. Запуск REST API

```bash
make run
# или
PYTHONPATH=src uvicorn vagus.layer3.api.main:app --host 0.0.0.0 --port 8000 --reload
```

API доступен по адресу: http://localhost:8000
Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc

### Аутентификация

По умолчанию доступны два пользователя:
- `admin` / `admin` (роль: admin)
- `user` / `user` (роль: user)

Получение токена:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

### WebSocket-стриминг с JWT

Для WebSocket-стриминга требуется access token в query string:

```text
ws://localhost:8000/api/v1/tasks/ws/<task_id>?token=<access_token>
```

## 4. Запуск Dashboard (Streamlit)

```bash
pip install streamlit
make run-dashboard
# или
PYTHONPATH=src:. streamlit run dashboard/main.py --server.port 8501
```

Dashboard: http://localhost:8501

## 5. Запуск Telegram Bot

```bash
pip install aiogram>=3.0
export TELEGRAM_BOT_TOKEN=your-bot-token
export VAGUS_API_URL=http://localhost:8000
make run-telegram
```

## 6. Запуск через Docker

```bash
# Все сервисы (API + Dashboard)
make docker-up

# С Telegram ботом
docker compose --profile telegram up -d

# Остановка
make docker-down
```

## 7. CLI

```bash
# Установка CLI
pip install typer rich httpx

# Логин
python -m vagus login --api-url http://localhost:8000

# Создание задачи
python -m vagus task create "Напиши функцию сложения" --type code

# Статус
python -m vagus task status <task-id>

# Список агентов
python -m vagus agent list
```

## 8. Тестирование

```bash
# Все тесты
make test

# Layer 1
make test-layer1

# Layer 2
make test-layer2

# Layer 3
make test-layer3

# Быстрая проверка
make verify
```

## 9. Структура конфигурации

```yaml
# configs/vagus.yaml
version: 1
name: Vagus Asistent
global:
  default_model: gpt-4o-mini
  log_level: INFO

providers:
  openai:
    endpoint: https://api.openai.com/v1
    models: [gpt-4o, gpt-4o-mini]

layer1:
  router:
    enable_cache: true
    enable_budgeting: true
    default_strategy: hybrid
```

## 10. Переменные окружения

| Переменная | Описание | По умолчанию |
|:-----------|:---------|:-------------|
| `OPENAI_API_KEY` | OpenAI API ключ | — |
| `ANTHROPIC_API_KEY` | Anthropic API ключ | — |
| `DEEPSEEK_API_KEY` | DeepSeek API ключ | — |
| `OPENROUTER_API_KEY` | OpenRouter API ключ | — |
| `GOOGLE_API_KEY` | Google API ключ | — |
| `VAGUS_SECRET_KEY` | Секрет для JWT | `vagus-dev-secret-...` |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | — |
| `VAGUS_API_URL` | URL REST API | `http://localhost:8000` |
