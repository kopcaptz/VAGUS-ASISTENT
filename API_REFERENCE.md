# API Reference (Layer 3 / WebSocket)

## Monitoring endpoints

### `GET /metrics`

Prometheus metrics endpoint (text format):

- `http_requests_total{method,endpoint,status}`
- `http_request_duration_seconds` (histogram)
- `websocket_connections_active`
- `task_execution_total{agent_type,status}`
- `llm_requests_total{provider,model,status}`
- `cache_hits_total`, `cache_misses_total`
- `circuit_breaker_state` (`0=closed`, `1=open`, `2=half-open`)

### `GET /health`

Базовый health endpoint:

```json
{"status":"ok"}
```

### `GET /health/detailed`

Детальный health report:

```json
{
  "status": "ok|degraded|failed",
  "timestamp": "2026-02-19T00:00:00+00:00",
  "thresholds": {
    "disk_free_percent_min": 10.0,
    "memory_usage_percent_max": 90.0,
    "check_timeout_seconds": 2.0,
    "disk_path": "."
  },
  "checks": {
    "database": {"status": "ok"},
    "redis": {"status": "ok|failed|skipped"},
    "llm_providers": {"status": "ok|degraded|failed"},
    "secrets_manager": {"status": "ok|failed"},
    "disk_space": {"status": "ok|failed"},
    "memory_usage": {"status": "ok|failed|degraded"}
  }
}
```

## WebSocket stream

- Endpoint: `WS /api/v1/tasks/ws/{task_id}?token=<access_token>`
- Назначение: стриминг статуса/результата задачи
- Требуется валидный JWT access token

## WebSocket hardening limits

| Параметр | Значение по умолчанию |
|:--|:--|
| `max_message_size_mb` | `10` MB |
| `ping_interval_seconds` | `30` |
| `ping_timeout_seconds` | `60` |
| `max_messages_per_minute` | `100` |

Конфигурация:

```yaml
websocket:
  max_message_size_mb: 10
  ping_interval_seconds: 30
  ping_timeout_seconds: 60
```

## WebSocket close codes

| Code | Meaning | Когда используется |
|:--|:--|:--|
| `1000` | Normal closure | Успешное завершение, task not found, heartbeat timeout |
| `1008` | Policy violation | Невалидный/отсутствующий токен |
| `1009` | Message too big | Превышен лимит размера входящего сообщения |
| `1011` | Internal error | Ошибка задачи или внутренняя ошибка сервера |
| `1013` | Try again later | Превышен rate limit |

## Audit log endpoint

- Endpoint: `GET /api/v1/tasks/ws/audit-log`
- Access: `admin only`
- Query params:
  - `limit` (1..1000, default 100)
  - `task_id` (optional)
  - `user_id` (optional)
  - `event_type` (optional)

События сохраняются в SQLite таблицу `websocket_audit_log`:
- `connect` (подключение)
- `message_sent` (исходящее сообщение от сервера)
- `message_received` (входящее сообщение от клиента)
- `close` (закрытие соединения)
- `rate_limit_exceeded`, `message_too_big`, `pong_timeout`

## Security enhancements

### Admin IP whitelist

- Middleware: `IPWhitelistMiddleware`
- Scope: только пути `/api/v1/admin/*`
- При нарушении: HTTP `403` + запись в лог приложения

Конфигурация:

```yaml
security:
  admin_ip_whitelist:
    - "127.0.0.1"
    - "192.168.1.0/24"
```

### Request signing (CLI → API)

- CLI отправляет подпись HMAC-SHA256 для HTTP-запросов
- Заголовки:
  - `X-Vagus-Client-Id`
  - `X-Vagus-Timestamp`
  - `X-Vagus-Signature`
- Креды клиента создаются автоматически при первом запуске:
  - `~/.vagus/client_credentials.json`

Серверная проверка включается конфигом:

```yaml
security:
  enable_request_signing: true
  request_signing_ttl_seconds: 300
```

### JWT secret rotation

Конфигурация:

```yaml
jwt:
  secret_rotation_days: 30
  max_old_secrets: 3
```

- Новый секрет используется для подписания новых токенов
- Старые секреты сохраняются для graceful валидации ранее выпущенных токенов

### Unified audit trail

- Endpoint: `GET /api/v1/admin/audit-logs` (admin only)
- Таблица: `audit_log`
- Поля: `timestamp`, `user_id`, `action`, `resource`, `details`, `ip_address`
- Логируются:
  - API requests
  - CLI commands
  - WebSocket events
  - runtime config load/change events

### Role-based HTTP rate limiting

```yaml
security:
  rate_limit:
    anonymous_requests_per_minute: 10
    user_requests_per_minute: 100
    admin_requests_per_minute: 1000
    redis_url: null
```

- Если Redis недоступен или не настроен, используется in-memory sliding window backend.

## Error Handling & Resilience (Stage 4)

### Dead Letter Queue

#### `GET /api/v1/admin/dead-letter-queue`

- Access: `admin only`
- Query params:
  - `limit` (1..1000, default 100)
  - `status` (optional)
  - `agent_type` (optional)

Response item fields:
- `task_id`
- `agent_type`
- `error_message`
- `stack_trace`
- `timestamp`
- `retry_count`

#### `POST /api/v1/admin/dead-letter-queue/{task_id}/retry`

- Access: `admin only`
- Body (optional):

```json
{
  "prompt": "optional override",
  "task_type": "optional override",
  "metadata": {"retry_reason": "manual"}
}
```

#### `POST /api/v1/admin/dead-letter-queue/{task_id}/manual-fix`

- Access: `admin only`
- Body:

```json
{"note": "Fixed manually by admin"}
```

### Circuit Breakers dashboard API

#### `GET /api/v1/admin/circuit-breakers`

- Access: `admin only`
- Returns:
  - `breakers`: list with `provider_id`, `state`, `failure_count`, `last_failure_time`, `success_rate`, ...
  - `history`: state history snapshots for dashboard plotting

#### `POST /api/v1/admin/circuit-breakers/{provider_id}/reset`

- Access: `admin only`
- Manual reset for selected provider circuit breaker.

### Error analytics API

#### `GET /api/v1/admin/error-analytics`

- Access: `admin only`
- Query params:
  - `window_minutes` (1..1440, default 60)
  - `top_sources_limit` (1..100, default 10)
- Returns:
  - `error_rate_by_type` (transient/permanent/infrastructure)
  - `top_error_sources`
  - `correlation`
  - `recent_events`
