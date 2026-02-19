# Hot Reload Plugins

## Назначение

`HotReloadManager` автоматически перезагружает плагины при изменении файлов без остановки приложения.

## Как работает graceful reload

1. Менеджер замечает изменение файла плагина.
2. Загружает новую версию плагина.
3. Регистрирует новые hook callbacks.
4. Переключает выполнение на новые hooks.
5. Отвязывает старые hooks.

Пользовательские задачи продолжают выполняться без downtime.

## Конфигурация

```yaml
plugins:
  hot_reload:
    enabled: true
    watch_directories: ["./plugins", "~/.vagus/plugins"]
    debounce_ms: 500
```

## Watchdog и fallback

- Если `watchdog` доступен, используется файловый observer.
- Если `watchdog` отсутствует, можно вызывать `on_file_changed(...)` вручную из внешнего orchestrator.

## Программное использование

```python
from vagus.plugins.hot_reload import HotReloadConfig, HotReloadManager

manager = HotReloadManager(config=HotReloadConfig(enabled=True))
manager.start()
```
