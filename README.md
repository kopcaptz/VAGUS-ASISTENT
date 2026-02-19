# Vagus Asistent

Многослойная агентная система с мульти-модельным роутером LLM.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                   СЛОЙ 3: ИНТЕРФЕЙСЫ                        │
│  REST API (FastAPI) │ CLI (Typer) │ Dashboard │ Telegram    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              СЛОЙ 2: АГЕНТНАЯ СИСТЕМА                       │
│  TaskOrchestrator │ Agents (Researcher, Coder, Analyst)     │
│  EpisodicMemory │ SemanticMemory │ CommunicationLayer       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                 СЛОЙ 1: ЯДРО LLM                            │
│  LLMRouter │ 5 провайдеров │ 4 стратегии │ Cache │ Budget  │
│  Monitoring │ Fallback + Circuit Breaker                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              СЛОЙ 0: ФУНДАМЕНТ                              │
│  ConfigManager │ Pydantic Models │ Hot-Reload │ Logging     │
└─────────────────────────────────────────────────────────────┘
```

## Возможности

- **Слой 0**: Конфигурация (YAML + env), Pydantic-валидация, hot-reload
- **Слой 1**: Ядро LLM
  - Провайдеры: OpenAI, Anthropic, DeepSeek, OpenRouter, Google
  - Стратегии балансировки: cost, latency, quality, hybrid
  - Fallback с Circuit Breaker и exponential backoff
  - Кэширование с TTL, бюджетирование, мониторинг (SQLite)
- **Слой 2**: Агентная система
  - 3 агента: Researcher, Coder, Analyst
  - 2 типа памяти: Episodic (краткосрочная), Semantic (векторный поиск)
  - Параллельное и многошаговое выполнение задач
- **Слой 3**: Интерфейсы
  - REST API (FastAPI) с JWT-аутентификацией и усиленным WebSocket
  - CLI (Typer) с rich-форматированием
  - Web Dashboard (Streamlit, 4 страницы)
  - Telegram Bot (aiogram 3.x)

## Требования

- Python 3.10+
- pip

## Быстрый старт

```bash
# Клонирование
git clone https://github.com/kopcaptz/VAGUS-ASISTENT.git
cd VAGUS-ASISTENT

# Установка
pip install -r requirements.txt

# Настройка
cp .env.example .env
# Отредактируйте .env — добавьте API-ключи

# Запуск API
make run

# Или напрямую:
PYTHONPATH=src uvicorn vagus.layer3.api.main:app --reload --port 8000
```

## Запуск компонентов

```bash
# REST API
make run

# Dashboard (Streamlit)
make run-dashboard

# Telegram Bot
make run-telegram

# Docker (все сервисы)
make docker-up
```

## API Endpoints

| Метод | Эндпоинт | Описание |
|:------|:---------|:---------|
| POST | `/api/v1/auth/token` | Получить JWT-токен |
| POST | `/api/v1/auth/refresh` | Обновить access_token |
| POST | `/api/v1/tasks` | Создать задачу |
| GET | `/api/v1/tasks/{id}` | Статус задачи |
| GET | `/api/v1/tasks` | Список задач |
| DELETE | `/api/v1/tasks/{id}` | Отменить задачу |
| GET | `/api/v1/tasks/ws/audit-log` | WebSocket audit log (admin only) |
| GET | `/api/v1/admin/audit-logs` | Unified audit trail (admin only) |
| GET | `/api/v1/agents` | Список агентов |
| GET | `/api/v1/status` | Статус системы |
| WS | `/api/v1/tasks/ws/{id}` | WebSocket стриминг |
| GET | `/health` | Health check |

## WebSocket hardening

- Heartbeat: сервер отправляет `ping` каждые `30s`, соединение закрывается при отсутствии `pong` в течение `60s`
- Лимит входящего сообщения: `10 MB` (`1009 Message too big`)
- Rate limit на соединение: `100` входящих сообщений в минуту (`1013 Try again later`)
- Стандартные close codes:
  - `1000` — normal closure
  - `1008` — policy violation (например, невалидный токен)
  - `1009` — message too big
  - `1011` — internal error
  - `1013` — try again later (rate limit)
- Audit logging: события `connect`, `message_sent`, `close` записываются в SQLite (`websocket_audit_log`)

```yaml
websocket:
  max_message_size_mb: 10
  ping_interval_seconds: 30
  ping_timeout_seconds: 60
```

## Security hardening (Stage 2)

- IP whitelist для `admin` endpoint'ов (`/api/v1/admin/*`) с поддержкой CIDR
- Request signing для CLI (HMAC-SHA256, заголовки `X-Vagus-*`)
- JWT secret rotation:
  - автоматическая ротация каждые `N` дней
  - хранение истории старых секретов для graceful decode
- Secrets manager:
  - backend `local` (env + local JSON)
  - backend `vault` (опционально, c fallback на local)
- Unified audit trail (`audit_log` в SQLite):
  - API запросы
  - CLI команды и аргументы
  - WebSocket события
  - события загрузки runtime-конфигурации
- Role-based rate limiting:
  - Anonymous: `10 req/min`
  - User: `100 req/min`
  - Admin: `1000 req/min`
  - Redis backend (опционально), иначе in-memory

## CLI

```bash
# Аутентификация
vagus login --api-url http://localhost:8000

# Создание задачи
vagus task create "Найди информацию о Python"

# Статус задачи
vagus task status <task-id>

# Список задач
vagus task list

# Список агентов
vagus agent list

# Статус системы
vagus admin status
```

## Тестирование

```bash
# Все тесты (200+)
make test

# По слоям
make test-layer1
make test-layer2
make test-layer3

# Быстрая проверка
make verify
```

## Структура проекта

```
VAGUS-ASISTENT/
├── src/vagus/
│   ├── layer0/          # Конфигурация, логирование
│   ├── layer1/          # LLM Router, провайдеры, кэш, бюджет
│   ├── layer2/          # Агенты, оркестратор, память
│   └── layer3/          # REST API, CLI, каналы
│       ├── api/         # FastAPI + JWT + WebSocket
│       ├── cli/         # Typer CLI
│       └── channels/    # Telegram Bot
├── dashboard/           # Streamlit Dashboard
├── tests/               # 200+ тестов
├── configs/             # Конфигурация YAML
├── docs/                # Документация
├── Makefile             # Команды сборки
├── Dockerfile           # Multi-stage Docker
└── docker-compose.yml   # Все сервисы
```

## Документация

- [API_REFERENCE.md](API_REFERENCE.md) — REST/WS API (включая WebSocket hardening)
- [docs/layer1/](docs/layer1/) — Архитектура, API, конфигурация Layer 1
- [docs/LAYER2_PLAN.md](docs/LAYER2_PLAN.md) — План и результаты Layer 2
- [docs/LAYER3_DESIGN.md](docs/LAYER3_DESIGN.md) — Дизайн Layer 3
- [SETUP.md](SETUP.md) — Инструкция по установке

## Лицензия

MIT
