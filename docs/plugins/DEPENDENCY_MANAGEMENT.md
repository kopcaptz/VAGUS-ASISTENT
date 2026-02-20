# Dependency Management (Plugins)

Этот документ описывает управление зависимостями плагинов через API и Dashboard.

## Возможности

- Просмотр dependency graph и конфликтов для каждого плагина.
- Автоматическое разрешение конфликтов (`prefer-installed` / `prefer-required`).
- Ручное обновление dependency spec.
- Bulk update зависимостей по нескольким плагинам.
- Health checks (missing/conflict/ok) и рекомендации.
- Экспорт/импорт lock-файла (`requirements.txt`).

## API Endpoints

### Get Dependency Graph

- `GET /api/v1/plugins/{plugin_name}/dependencies`

Возвращает:

- список зависимостей
- install order
- graph/edges
- conflicts/missing

### Get Conflicts + Health

- `GET /api/v1/plugins/{plugin_name}/dependencies/conflicts`

Возвращает:

- конфликты и missing dependencies
- health checks (доступность/совместимость)
- рекомендации
- текущий lock content

### Auto Resolve

- `POST /api/v1/plugins/{plugin_name}/dependencies/resolve`

Пример:

```json
{
  "strategy": "prefer-installed",
  "dry_run": false,
  "pin_versions": true,
  "export_lock": true
}
```

### Manual Update

- `POST /api/v1/plugins/{plugin_name}/dependencies/update`

Пример:

```json
{
  "updates": {
    "requests": ">=2.31.0",
    "pydantic": "==2.12.0"
  },
  "pin_versions": false,
  "dry_run": false,
  "export_lock": true
}
```

Импорт lock:

```json
{
  "updates": {},
  "import_lock_content": "requests==2.31.0\npydantic==2.12.0\n",
  "pin_versions": true,
  "dry_run": false
}
```

### Bulk Update

- `POST /api/v1/plugins/dependencies/bulk-update`

Пример:

```json
{
  "operations": [
    {
      "plugin_name": "plugin-a",
      "updates": {"requests": "==2.31.0"},
      "pin_versions": true
    },
    {
      "plugin_name": "plugin-b",
      "updates": {"urllib3": ">=2.2.0"},
      "pin_versions": false
    }
  ],
  "dry_run": false,
  "rollback_on_error": true,
  "allow_conflicts": false,
  "export_lock": true
}
```

## Dashboard Workflow

В `Plugins -> Installed -> <plugin> -> Dependencies`:

1. Просмотрите graph, conflicts и health checks.
2. Нажмите `Auto-resolve conflicts` для автоматического исправления.
3. Используйте `Manual dependency update` для ручной корректировки версий.
4. Экспортируйте/импортируйте lock-файл.

Для массовых операций:

- используйте секцию `Bulk dependency management` в вкладке `Installed`.
- при включенном `Rollback on error` система откатит изменения при ошибке.
