# Vagus Asistent

Многослойная агентная система с мульти-модельным LLM роутером, REST API, WebSocket, CLI и Dashboard.

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│  Слой 3 — Интерфейс                                         │
│  REST API · WebSocket · CLI · Streamlit Dashboard · Telegram │
├──────────────────────────────────────────────────────────────┤
│  Слой 2 — Агентная система                                   │
│  TaskOrchestrator · ResearcherAgent · SkillSystem             │
├──────────────────────────────────────────────────────────────┤
│  Слой 1 — Ядро LLM                                          │
│  Router · Providers · Fallback · Cache · Budget · Monitoring │
├──────────────────────────────────────────────────────────────┤
│  Слой 0 — Инфраструктура                                     │
│  ConfigManager · Logging · Hot-reload                        │
└──────────────────────────────────────────────────────────────┘
```

## Возможности

| Слой | Компоненты |
|------|-----------|
| **Слой 0** | YAML-конфигурация, `.env` секреты, структурированный логгинг, hot-reload |
| **Слой 1** | Роутер с балансировкой (cost / latency / quality / hybrid), провайдеры (OpenAI, Anthropic, DeepSeek, OpenRouter, Google), Circuit Breaker, fallback-цепочки, кэш с TTL, бюджеты (день/месяц), мониторинг в SQLite |
| **Слой 2** | TaskOrchestrator (state machine), ResearcherAgent, SkillSystem (search_web, execute_python, read_file), Pub/Sub коммуникация |
| **Слой 3** | FastAPI REST API, JWT-аутентификация, WebSocket для real-time обновлений, CLI-клиент, Streamlit Dashboard, rate limiting |

## Быстрый старт

### Локальная разработка

```bash
# 1. Клонируйте репозиторий
git clone https://github.com/your-org/vagus-asistent.git
cd vagus-asistent

# 2. Создайте виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# 3. Установите зависимости
pip install -r requirements.txt

# 4. Настройте окружение
cp .env.example .env
# Отредактируйте .env — добавьте API-ключи провайдеров

# 5. Запустите тесты
make test

# 6. Запустите API-сервер
PYTHONPATH=src uvicorn vagus.layer3.api.app:app --reload --port 8000
```

### Docker (Production)

```bash
# 1. Настройте окружение
cp .env.production .env
# Отредактируйте .env — замените все CHANGE-ME значения

# 2. Сгенерируйте SSL-сертификаты (для разработки — self-signed)
make certs

# 3. Полный деплой
make deploy

# Или по шагам:
make build        # собрать образы
make run          # запустить сервисы
make status       # проверить статус
make logs         # просмотр логов
```

После запуска доступны:

| Сервис | URL | Описание |
|--------|-----|----------|
| API | http://localhost:8000 | REST API + Swagger UI (/docs) |
| Dashboard | http://localhost:8501 | Streamlit Dashboard |
| Grafana | http://localhost:3000 | Мониторинг (admin / vagus) |
| Prometheus | http://localhost:9090 | Метрики |

## API

### Аутентификация

```bash
# Получить токен
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your-password"}'

# Ответ:
# {"access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "bearer"}

# Обновить токен
curl -X POST http://localhost:8000/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

### Задачи

```bash
# Создать задачу
curl -X POST http://localhost:8000/tasks \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Найди информацию о Python", "task_type": "research"}'

# Ответ: {"task_id": "uuid-...", "status": "pending"}

# Проверить статус
curl http://localhost:8000/tasks/{task_id}
```

### WebSocket

```python
import asyncio
import websockets

async def watch_task(task_id: str):
    async with websockets.connect(f"ws://localhost:8000/ws/{task_id}") as ws:
        async for message in ws:
            print(message)

asyncio.run(watch_task("your-task-id"))
```

### Health Check

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Python SDK

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

    async for chunk in router.route_request("Привет!", stream=True):
        print(chunk.get("content", ""), end="")

asyncio.run(main())
```

## CLI

```bash
# Логин
python -m vagus.layer3.cli login --username admin --password secret

# Создать задачу
python -m vagus.layer3.cli create-task --prompt "Analyze data" --type research

# Статус задачи
python -m vagus.layer3.cli status --task-id <uuid>
```

## Структура проекта

```
vagus-asistent/
├── src/vagus/
│   ├── layer0/              # Конфигурация, логирование
│   │   ├── config/          # ConfigManager, Pydantic-модели
│   │   └── logging/         # Структурированный логгинг
│   ├── layer1/              # Ядро LLM
│   │   ├── router/          # LLMRouter, RequestHandler
│   │   ├── providers/       # OpenAI, Anthropic, DeepSeek, Google, OpenRouter
│   │   ├── balancing/       # Cost, Latency, Quality, Hybrid стратегии
│   │   ├── fallback/        # CircuitBreaker, RetryManager, FallbackChain
│   │   ├── cache/           # CacheService с TTL
│   │   ├── budgeting/       # BudgetingService (дневные/месячные лимиты)
│   │   └── monitoring/      # MetricsCollector, CostTracker, SQLite
│   ├── layer2/              # Агентная система
│   │   ├── agents/          # BaseAgent, ResearcherAgent
│   │   ├── communication/   # Pub/Sub (asyncio.Queue → Redis)
│   │   ├── skills/          # SkillSystem (search_web, execute_python)
│   │   ├── memory/          # Контекстная память (WIP)
│   │   └── orchestrator.py  # TaskOrchestrator (state machine)
│   └── layer3/              # Пользовательский интерфейс
│       ├── api/             # FastAPI REST API
│       ├── auth/            # JWT аутентификация
│       ├── websocket/       # WebSocket real-time обновления
│       ├── cli/             # CLI-клиент
│       └── dashboard/       # Streamlit / Dashboard клиент
├── tests/
│   ├── layer1/              # Unit + Integration тесты Layer 1
│   ├── layer2/              # Тесты агентов, навыков, E2E
│   └── layer3/              # Тесты API, Auth, WebSocket, CLI, Dashboard
├── configs/                 # YAML конфигурация
├── grafana/                 # Dashboards + Provisioning для Grafana
├── docker-compose.yml       # Все сервисы
├── Dockerfile               # Multi-stage сборка
├── nginx.conf               # Reverse proxy + SSL + rate limiting
├── prometheus.yml            # Конфигурация Prometheus
├── Makefile                 # build / run / test / deploy
├── .env.production          # Шаблон production-окружения
└── requirements.txt         # Python-зависимости
```

## Тестирование

```bash
make test           # все тесты
make test-unit      # unit-тесты всех слоёв
make test-layer3    # тесты Layer 3 (API, Auth, WS, CLI, Dashboard)
make test-cov       # тесты + coverage report
```

Текущее покрытие: **44 теста** по всем слоям.

## Docker-сервисы

| Сервис | Образ | Описание |
|--------|-------|----------|
| `api` | custom | FastAPI + Uvicorn (основной API) |
| `redis` | redis:7-alpine | Кэш + очереди |
| `postgres` | postgres:16-alpine | Хранение задач, пользователей |
| `nginx` | nginx:1.27-alpine | Reverse proxy, SSL, rate limiting |
| `streamlit` | custom | Streamlit Dashboard |
| `telegram-bot` | custom | Telegram-бот |
| `prometheus` | prom/prometheus | Сбор метрик |
| `grafana` | grafana/grafana | Визуализация метрик |

## Мониторинг

Grafana дашборд **Vagus Overview** включает:

- **API Request Rate** — запросы в секунду по endpoint
- **Response Latency** — p50 / p95 время ответа
- **Active Tasks** — текущие задачи в обработке
- **Tasks Completed** — общий счётчик завершённых задач
- **LLM Provider Errors** — ошибки по провайдерам
- **LLM Token Usage** — потребление токенов
- **LLM Cost (Daily)** — стоимость за день по провайдерам

## Troubleshooting

### API не стартует

```bash
# Проверьте логи
make logs-api

# Убедитесь, что PostgreSQL и Redis готовы
docker compose ps

# Проверьте health endpoint
curl http://localhost:8000/health
```

### Ошибки подключения к БД

```bash
# Проверьте, что PostgreSQL запущен и доступен
docker compose exec postgres pg_isready -U vagus

# Пересоздайте БД при необходимости
make db-reset
```

### Rate limiting (429 Too Many Requests)

Rate limit настроен на двух уровнях:
1. **Nginx**: 30 req/s для API, 5 req/s для auth
2. **FastAPI**: 60 запросов / 60 секунд на IP

Для увеличения лимитов измените значения в `nginx.conf` и `src/vagus/layer3/api/app.py`.

### SSL-сертификаты

Для production используйте Let's Encrypt:

```bash
# Установите certbot
apt install certbot python3-certbot-nginx

# Получите сертификат
certbot --nginx -d vagus.example.com

# Обновите пути в nginx.conf
```

Для разработки:

```bash
make certs
```

### Тесты не проходят

```bash
# Убедитесь, что зависимости установлены
pip install -r requirements.txt

# Запустите с подробным выводом
PYTHONPATH=src python3 -m pytest tests/ -v --tb=long
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|-------------|----------|
| `VAGUS_JWT_SECRET` | dev-secret | Секретный ключ для JWT |
| `VAGUS_ENV` | development | Окружение (production / development) |
| `VAGUS_LOG_LEVEL` | INFO | Уровень логирования |
| `DATABASE_URL` | — | PostgreSQL connection string |
| `REDIS_URL` | — | Redis connection string |
| `OPENAI_API_KEY` | — | Ключ OpenAI API |
| `ANTHROPIC_API_KEY` | — | Ключ Anthropic API |
| `DEEPSEEK_API_KEY` | — | Ключ DeepSeek API |
| `TELEGRAM_BOT_TOKEN` | — | Токен Telegram-бота |

Полный список — в `.env.production`.

## Лицензия

MIT
