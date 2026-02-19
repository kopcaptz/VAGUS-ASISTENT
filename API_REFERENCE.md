# API Reference (Layer 3 / WebSocket)

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
