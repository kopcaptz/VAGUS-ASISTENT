# Plugin Marketplace

## Что это

Marketplace предоставляет каталог плагинов с поиском, версиями, рейтингами и загрузкой.

## Клиент

`MarketplaceClient` поддерживает:

- `search_plugins(query, category, limit)`
- `get_plugin_details(plugin_id)`
- `download_plugin(plugin_id, version)`
- `get_plugin_versions(plugin_id)`
- `get_categories()`

Дополнительно:

- in-memory кэш результатов (`cache_ttl_hours`),
- offline fallback (возврат кэшированных снапшотов при недоступности сервиса).

## API сервер (микросервис)

`create_marketplace_app(...)` поднимает FastAPI приложение со SQLite backend:

- `GET /plugins/search`
- `GET /plugins/{plugin_id}`
- `GET /plugins/{plugin_id}/versions`
- `GET /plugins/{plugin_id}/download`
- `POST /plugins/upload`
- `GET /plugins/categories`

В БД хранятся:

- метаданные плагинов,
- история версий,
- рейтинги и отзывы.

## Пример загрузки

```python
from vagus.plugins.marketplace import MarketplaceClient

client = MarketplaceClient(url="http://localhost:9000")
plugins = client.search_plugins(query="analytics", category="productivity", limit=10)
details = client.get_plugin_details("analytics_booster")
```
