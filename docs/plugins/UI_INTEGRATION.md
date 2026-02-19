# Plugin UI Integration

## Dashboard page

Страница `dashboard/pages/8_Plugins.py` добавляет web-интерфейс управления плагинами:

- список установленных плагинов,
- поиск в marketplace,
- визуализация графа зависимостей,
- просмотр аналитики и логов.

## Вспомогательные UI функции

`dashboard/utils/plugins.py` содержит тестируемые helper-функции:

- `summarize_installed_plugins`
- `filter_marketplace_plugins`
- `build_dependency_edges`
- `format_plugin_logs`

## Дальнейшее развитие

Рекомендуется подключить backend endpoints для:

- install/uninstall plugin,
- enable/disable plugin,
- live plugin logs streaming,
- dependency graph rendering через интерактивные граф-библиотеки.
