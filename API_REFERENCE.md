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

### `GET /api/v1/admin/memory-stats` (admin only)

Runtime memory profiler snapshot + leak detection report:

Query params:
- `refresh` (bool, default `true`) — принудительно собрать новую snapshot
- `history_limit` (1..1000, default `60`) — сколько последних точек вернуть

Response (пример):

```json
{
  "current": {
    "timestamp": "2026-02-19T00:00:00+00:00",
    "process_memory_mb": 180.42,
    "python_object_count": 45213,
    "gc_count": {"gen0": 21, "gen1": 2, "gen2": 0},
    "gc_stats": [],
    "top_object_types": [{"type": "dict", "count": 10234}],
    "leak_signal": {
      "detected": false,
      "growth_mb": 12.8,
      "threshold_mb": 100.0,
      "window_seconds": 300
    }
  },
  "history": [],
  "history_size": 1,
  "leak_policy": {"threshold_mb": 100.0, "window_seconds": 300},
  "monitoring_active": true
}
```

## Plugin marketplace & search (admin only)

### `GET /api/v1/plugins/marketplace/search?q=<query>&category=<category>&limit=<n>`

Поиск плагинов в marketplace (с кэшированием и offline fallback):

```json
[
  {
    "plugin_id": "marketplace-demo",
    "name": "Marketplace Demo",
    "description": "Plugin description",
    "category": "automation",
    "author": "Marketplace Team",
    "latest_version": "1.2.3",
    "download_url": "https://plugins.example/plugin.zip",
    "avg_rating": 4.8,
    "review_count": 120
  }
]
```

### `GET /api/v1/plugins/marketplace/categories`

Возвращает список категорий marketplace:

```json
["automation", "ai", "monitoring"]
```

### `GET /api/v1/plugins/marketplace/trending?limit=10`

Возвращает популярные (trending) плагины в формате, аналогичном search.

### `GET /api/v1/plugins/marketplace/{plugin_id}`

Детальная карточка плагина:

```json
{
  "plugin_id": "marketplace-demo",
  "name": "Marketplace Demo",
  "metadata": {"downloads": 1024},
  "versions": [{"version": "1.2.3"}],
  "reviews": [{"rating": 5, "review": "Great plugin"}]
}
```

### `POST /api/v1/plugins/marketplace/{plugin_id}/install`

Установка plugin_id напрямую из marketplace.

Body (optional):

```json
{
  "version": "1.2.3"
}
```

### `GET /api/v1/plugins/{plugin_name}/dependencies`

Dependency view для установленного плагина:

```json
{
  "plugin_name": "main-plugin",
  "dependencies": ["dep-plugin>=2.0.0"],
  "install_order": ["dep-plugin", "main-plugin"],
  "graph": {"main-plugin": ["dep-plugin"], "dep-plugin": []},
  "edges": [{"source": "main-plugin", "target": "dep-plugin"}],
  "conflicts": {"dep-plugin": [">=2.0.0"]},
  "missing_dependencies": []
}
```

### `GET /api/v1/plugins/statistics`

Агрегированная статистика по installed/plugins/trending:

```json
{
  "summary": {
    "installed_total": 5,
    "enabled_total": 4,
    "disabled_total": 1,
    "error_total": 0,
    "marketplace_offline_mode": false
  },
  "popularity": [],
  "trending": []
}
```

## Plugin Dependency Management (admin only)

### `GET /api/v1/plugins/{plugin_name}/dependencies/conflicts`

Возвращает конфликтные зависимости + health checks + рекомендации:

```json
{
  "plugin_name": "main-plugin",
  "conflicts": {"pip": [">=1000.0"]},
  "missing_dependencies": [],
  "health_checks": [
    {
      "dependency_name": "pip",
      "required_spec": ">=1000.0",
      "installed_version": "24.0",
      "available": true,
      "compatible": false,
      "status": "conflict",
      "recommendation": "Align 'pip' to required spec '>=1000.0' (currently '24.0')."
    }
  ],
  "recommendations": ["Resolve 'pip' with compatible spec: >=1000.0"],
  "lock_file_path": "/.../requirements.txt",
  "lock_content": "pip>=1000.0\n"
}
```

### `POST /api/v1/plugins/{plugin_name}/dependencies/resolve`

Автоматическое разрешение конфликтов:

```json
{
  "strategy": "prefer-installed",
  "dry_run": false,
  "pin_versions": true,
  "export_lock": true
}
```

### `POST /api/v1/plugins/{plugin_name}/dependencies/update`

Ручное обновление dependency spec и import/export lock:

```json
{
  "updates": {"requests": ">=2.31.0"},
  "pin_versions": false,
  "dry_run": false,
  "export_lock": true
}
```

### `POST /api/v1/plugins/dependencies/bulk-update`

Массовое обновление зависимостей с rollback:

```json
{
  "operations": [
    {"plugin_name": "plugin-a", "updates": {"requests": "==2.31.0"}, "pin_versions": true}
  ],
  "dry_run": false,
  "rollback_on_error": true,
  "allow_conflicts": false,
  "export_lock": true
}
```

## Plugin Hot-Reload & Monitoring (admin only)

### `GET /api/v1/plugins/hot-reload/status`

Возвращает runtime статус hot-reload, health/performance snapshot и alerts.

### `POST /api/v1/plugins/hot-reload/enable`

Включает file watcher для hot-reload.

### `POST /api/v1/plugins/hot-reload/disable`

Выключает file watcher.

### `GET /api/v1/plugins/hot-reload/logs`

Query params:

- `limit` (1..1000)
- `plugin_name` (optional)
- `event_type` (optional)

### `GET /api/v1/plugins/{plugin_name}/reload-history`

История reload событий конкретного плагина.

### `POST /api/v1/plugins/{plugin_name}/reload-now`

Принудительная перезагрузка плагина.

### `WS /api/v1/plugins/ws/updates?token=<admin_access_token>`

Real-time stream событий мониторинга:

- `connection_ack`
- `status_snapshot`
- `hot_reload_event`
- `plugin_alert`

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

## Performance Optimizations (Stage 5) - config snippets

```yaml
layer1:
  http:
    max_connections: 100
    max_keepalive_connections: 20
    keepalive_expiry: 5.0
  cache:
    secondary:
      enabled: true
      redis_url: redis://localhost:6379/0
      sqlite_fallback_path: cache_fallback.db
      llm_responses_ttl_seconds: 3600
      provider_health_ttl_seconds: 120
      rate_limit_counter_ttl_seconds: 60
      session_data_ttl_seconds: 3600

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

monitoring:
  memory_profiler:
    enabled: true
    interval_seconds: 30
    leak_threshold_mb: 100.0
    leak_window_seconds: 300
```
