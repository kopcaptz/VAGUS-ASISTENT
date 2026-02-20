# Plugin Monitoring

Документ описывает мониторинг плагинов и hot-reload через API и Dashboard.

## Что доступно

- Hot-reload status и управление watcher (`enable/disable`).
- Логи hot-reload событий и per-plugin reload history.
- Ручной reload плагина через API.
- Runtime health snapshot (error rate, memory usage, execution time).
- Performance ranking + рекомендации.
- Алерты (локальные события + snapshot конфигурации каналов).
- WebSocket stream для real-time обновлений.

## Hot-Reload API

- `GET /api/v1/plugins/hot-reload/status`
- `POST /api/v1/plugins/hot-reload/enable`
- `POST /api/v1/plugins/hot-reload/disable`
- `GET /api/v1/plugins/hot-reload/logs`
- `GET /api/v1/plugins/{plugin_name}/reload-history`
- `POST /api/v1/plugins/{plugin_name}/reload-now`

### Пример status

```json
{
  "enabled": true,
  "running": true,
  "watchdog_available": true,
  "watch_directories": ["./plugins", "~/.vagus/plugins"],
  "debounce_ms": 500,
  "events_total": 20,
  "recent_logs": [],
  "plugin_health": [],
  "performance": {
    "by_memory": [],
    "by_execution_time": [],
    "by_error_rate": [],
    "recommendations": []
  },
  "alerts": [],
  "alerting": {
    "channels": {"email": false, "telegram": false, "webhook": false},
    "escalation_policies": []
  }
}
```

## Real-time updates

WebSocket endpoint:

- `WS /api/v1/plugins/ws/updates?token=<admin_access_token>`

Сообщения:

- `connection_ack`
- `status_snapshot`
- `hot_reload_event`
- `plugin_alert`

## Alerting and escalation

Текущий API возвращает snapshot alerting-конфигурации из runtime config:

- каналы (`email`, `telegram`, `webhook`)
- `escalation_policies`

Это позволяет Dashboard показывать, какие каналы/политики активны в окружении.
