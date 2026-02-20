# Hot Reload UI

Вкладка `Plugins -> Hot Reload` в Dashboard предоставляет интерфейс управления hot-reload и мониторингом.

## Возможности UI

- Просмотр status hot-reload (`enabled`, `running`, `watchdog_available`, event counters).
- Кнопки управления:
  - `Enable hot-reload`
  - `Disable hot-reload`
  - `Refresh`
- Просмотр hot-reload логов с фильтрами (`plugin_name`, `event_type`, `limit`).
- График reload events.
- Ручной reload плагина (`Reload now`) и просмотр history.
- Health dashboard:
  - memory usage
  - average execution time
  - error rate
- Performance рекомендации.
- Live panel на WebSocket (`/api/v1/plugins/ws/updates`) для real-time событий.

## Live Events panel

WebSocket компонент в UI:

- автоматически переподключается при разрыве,
- отображает входящие события,
- показывает push notifications для критичных событий:
  - `plugin_reload_failed`
  - `plugin_alert`
  - `manual_reload`

## Ожидаемый workflow

1. Включить hot-reload.
2. Проверить `status` и `watchdog_available`.
3. Наблюдать за событиями в live panel и логах.
4. При ошибках выполнить `Reload now` и проверить `reload history`.
5. Использовать health/performance блок для анализа проблемных плагинов.
