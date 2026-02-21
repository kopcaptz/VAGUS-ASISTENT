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
│  EpisodicMemory │ SemanticMemory │ MemoryManager │ ArtifactKnowledgeBase │
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
  - Fallback с Circuit Breaker и автоматическим retry (exponential backoff)
  - Кэширование с TTL, бюджетирование, мониторинг (SQLite)
- **Слой 2**: Агентная система
  - 3 агента: Researcher, Coder, Analyst
  - Память: Episodic (краткосрочная), Semantic (векторный поиск), MemoryManager, ArtifactKnowledgeBase
  - Параллельное и многошаговое выполнение задач
  - Dead Letter Queue (DLQ), task timeouts, graceful degradation
- **Слой 3**: Интерфейсы
  - REST API (FastAPI) с JWT-аутентификацией и усиленным WebSocket
  - CLI (Typer) с rich-форматированием
  - Web Dashboard (Streamlit, 7 страниц)
  - Telegram Bot (aiogram 3.x)
  - Monitoring & Observability:
    - Prometheus endpoint `/metrics`
    - Detailed dependency health `/health/detailed`
    - Structured JSON logging (trace_id/request_id)
    - Alerting engine (Telegram/SMTP/Webhook)
    - Grafana dashboard templates + Prometheus stack

## Требования

- Python 3.12+
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
| GET | `/api/v1/admin/dead-letter-queue` | Dead Letter Queue (admin only) |
| POST | `/api/v1/admin/dead-letter-queue/{task_id}/retry` | Retry failed task from DLQ (admin only) |
| POST | `/api/v1/admin/dead-letter-queue/{task_id}/manual-fix` | Mark DLQ task as manually fixed (admin only) |
| GET | `/api/v1/admin/circuit-breakers` | Circuit breaker dashboard data (admin only) |
| POST | `/api/v1/admin/circuit-breakers/{provider_id}/reset` | Manual circuit breaker reset (admin only) |
| GET | `/api/v1/admin/error-analytics` | Error classification analytics (admin only) |
| GET | `/api/v1/admin/memory-stats` | Runtime memory profiling + leak detection (admin only) |
| GET | `/api/v1/agents` | Список агентов |
| GET | `/api/v1/status` | Статус системы |
| WS | `/api/v1/tasks/ws/{id}` | WebSocket стриминг |
| GET | `/health` | Health check |
| GET | `/health/detailed` | Детальный health check (зависимости + thresholds) |
| GET | `/metrics` | Prometheus metrics endpoint |

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

## Monitoring & Observability (Stage 3)

- **Prometheus metrics**: `GET /metrics`
  - `http_requests_total` (labels: `method`, `endpoint`, `status`)
  - `http_request_duration_seconds` (histogram)
  - `websocket_connections_active` (gauge)
  - `task_execution_total` (labels: `agent_type`, `status`)
  - `llm_requests_total` (labels: `provider`, `model`, `status`)
  - `cache_hits_total`, `cache_misses_total`
  - `circuit_breaker_state` (`0=closed`, `1=open`, `2=half-open`)
- **Detailed health checks**: `GET /health/detailed`
  - SQLite connectivity
  - Redis connectivity (если настроен)
  - LLM providers availability
  - Secrets manager connectivity
  - Disk space / Memory usage (с threshold-конфигом)
- **Structured logging**
  - JSON поля: `timestamp`, `level`, `message`, `trace_id`, `request_id`, `user_id`, `agent_id`, `duration_ms`, `component`
  - Интеграция: FastAPI middleware, CLI и WebSocket paths
- **Alerting**
  - Правила: high error rate, high latency, circuit breaker open, low disk space, provider down
  - Каналы: Telegram bot, Email (SMTP), Webhook
  - YAML-конфиг: `configs/alerting.yaml.example`
- **Grafana + Prometheus**
  - assets: `monitoring/grafana/*.json`
  - stack: `monitoring/docker-compose.yml`

## Error Handling & Resilience (Stage 4)

- **Dead Letter Queue (DLQ)** в SQLite (`dead_letter_queue`)
  - Поля: `task_id`, `agent_type`, `error_message`, `stack_trace`, `timestamp`, `retry_count`
  - Admin API: просмотр, retry, manual fix
- **Automatic retry** c exponential backoff:
  - интервалы: `1s, 2s, 4s, 8s, 16s`
  - максимум `5` попыток
  - retryable ошибки по ключам (`timeout`, `rate_limit`, `network_error`)
- **Task timeout per agent type**:
  - `researcher=300s`, `coder=600s`, `analyst=180s`
  - автоматическая отмена через `asyncio.wait_for`
- **Graceful degradation**:
  - Researcher unavailable → web search fallback
  - Coder unavailable → pseudocode fallback
  - Analyst unavailable → simple summary fallback
  - health-check перед назначением задачи
- **Circuit Breaker dashboard**:
  - realtime state (`closed/open/half-open`), failure count, last failure time, success rate
  - manual reset
  - history charts
- **Error analytics**:
  - классификация: transient / permanent / infrastructure
  - error rate by type, top sources, correlation snapshot

## Performance Optimizations (Stage 5)

- **Shared HTTP connection pooling (Layer 1 providers)**
  - Singleton `httpx.AsyncClient` pool для OpenAI/Anthropic/DeepSeek/OpenRouter
  - Конфиг:
    ```yaml
    layer1:
      http:
        max_connections: 100
        max_keepalive_connections: 20
        keepalive_expiry: 5.0
    ```
- **Secondary cache: Redis + SQLite fallback**
  - In-memory cache остаётся primary
  - Secondary namespaces:
    - `llm_response` (TTL 1h)
    - `provider_health`
    - `rate_limit_counter`
    - `session_data`
  - Конфиг:
    ```yaml
    layer1:
      cache:
        secondary:
          enabled: true
          redis_url: redis://localhost:6379/0
          sqlite_fallback_path: cache_fallback.db
          llm_responses_ttl_seconds: 3600
          provider_health_ttl_seconds: 120
          rate_limit_counter_ttl_seconds: 60
          session_data_ttl_seconds: 3600
    ```
- **SQLite query optimization**
  - Индексы `idx_metrics_timestamp`, `idx_metrics_provider`
  - Совместимый индекс `idx_audit_log_timestamp` (если таблица `audit_log` доступна в БД)
  - Оптимизированные выборки с `ORDER BY ... LIMIT`
  - Периодический `VACUUM` после cleanup
- **Memory profiler + leak detection**
  - Endpoint: `GET /api/v1/admin/memory-stats`
  - Мониторинг:
    - RSS process memory
    - Python object count / top object types
    - GC stats
    - leak signal при росте `>100MB` за `5 минут` (настраивается)
- **Horizontal scalability in orchestrator**
  - Stateless mode config
  - Shared task queue (Redis, fallback in-memory)
  - Distributed locking (Redis) для предотвращения двойного исполнения задач
  - Конфиг:
    ```yaml
    layer2:
      cluster:
        enabled: false
        node_id: node-local
        stateless_agents: true
        shared_task_queue:
          enabled: false
          redis_url: redis://localhost:6379/0
        distributed_locking:
          enabled: false
          redis_url: redis://localhost:6379/0
          lock_ttl_seconds: 900
    ```
- **Load testing scripts**
  - `load_testing/api_load_test.py` (Locust сценарии)
  - `load_testing/websocket_load_test.py` (long-running WS connections)
  - `load_testing/cli_load_test.py` (concurrent CLI workload)
  - JSON reports в `load_testing/reports/`
- **Performance benchmarking**
  - Модуль: `src/vagus/benchmarking/performance_benchmark.py`
  - Scenarios:
    - provider latency
    - agent execution time
    - cache hit/miss performance
    - database query performance
  - Сохранение результатов + auto-run helper при изменении исходников

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
# Все тесты (280+)
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
│   │   └── memory/      # Episodic, Semantic, Procedural, MemoryManager, ArtifactKnowledgeBase
│   └── layer3/          # REST API, CLI, каналы
│       ├── api/         # FastAPI + JWT + WebSocket
│       ├── cli/         # Typer CLI
│       └── channels/    # Telegram Bot
├── dashboard/           # Streamlit Dashboard (Tasks/Monitoring/Agents/Settings/Performance/CircuitBreakers/ErrorAnalytics)
├── monitoring/          # Grafana dashboards + Prometheus config + compose
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
