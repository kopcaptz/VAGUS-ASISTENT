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

websocket:
  max_message_size_mb: 10
  ping_interval_seconds: 30
  ping_timeout_seconds: 60

security:
  admin_ip_whitelist:
    - "127.0.0.1"
    - "192.168.1.0/24"
  enable_request_signing: false
  request_signing_ttl_seconds: 300
  request_signing_credentials_path: "~/.vagus/client_credentials.json"
  audit_db_path: "audit_trail.db"
  rate_limit:
    anonymous_requests_per_minute: 10
    user_requests_per_minute: 100
    admin_requests_per_minute: 1000
    redis_url: null

jwt:
  secret_rotation_days: 30
  max_old_secrets: 3

secrets:
  backend: local # local | vault
  vault_addr: http://localhost:8200
  vault_token: ""

layer1:
  router:
    enable_cache: true
    enable_budgeting: true
    default_strategy: hybrid
```

### WebSocket limits и close codes

- Максимальный размер входящего WS-сообщения: `10 MB` (close code `1009`)
- Heartbeat: ping каждые `30` секунд, timeout pong: `60` секунд
- Rate limit: `100` сообщений в минуту на соединение (close code `1013`)
- Невалидный токен: close code `1008`
- Внутренняя ошибка: close code `1011`

### Security enhancements

- IP whitelist применяется к `/api/v1/admin/*`
- CLI request signing:
  - клиент хранит `client_id/client_secret` в `~/.vagus/client_credentials.json`
  - сервер валидирует подпись HMAC-SHA256 через middleware
- JWT secret rotation:
  - авто-ротация по `jwt.secret_rotation_days`
  - сохранение `jwt.max_old_secrets` прошлых ключей
- Unified audit trail endpoint:
  - `GET /api/v1/admin/audit-logs` (admin only)

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

## 11. Monitoring & Observability

### Prometheus endpoint

- Метрики доступны на `GET /metrics`
- Формат: Prometheus exposition format

Проверка:

```bash
curl http://localhost:8000/metrics
```

### Detailed health endpoint

- Детальный health check: `GET /health/detailed`
- Включает проверки:
  - SQLite
  - Redis (если настроен)
  - LLM providers
  - Secrets manager
  - Disk / Memory thresholds

Проверка:

```bash
curl http://localhost:8000/health/detailed
```

### Threshold configuration

```yaml
monitoring:
  health:
    thresholds:
      disk_free_percent_min: 10.0
      memory_usage_percent_max: 90.0
      check_timeout_seconds: 2.0
      disk_path: "."
```

### Alerting configuration

- Шаблон конфигурации: `configs/alerting.yaml.example`
- Каналы: Telegram, SMTP email, Webhook

### Grafana + Prometheus stack

```bash
cd monitoring
docker compose up -d
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Дашборды автоматически подхватываются из `monitoring/grafana/`
