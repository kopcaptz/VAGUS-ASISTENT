# Vagus Asistent — Production Deployment

## Prerequisites

- **Docker** 20.10+
- **Docker Compose** v2.1+ (для `condition: service_completed_successfully` при миграциях)
- **Образ** — `.env` с секретами и LLM API keys (см. `.env.example`)

## Environment Variables

Обязательные переменные для production:

| Переменная | Описание | Пример |
|------------|----------|--------|
| `POSTGRES_USER` | Пользователь PostgreSQL | `vagus` |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL | (секрет) |
| `POSTGRES_HOST` | Хост PostgreSQL | `postgres` (в Docker) |
| `POSTGRES_DB` | Имя БД | `vagus_db` |
| `REDIS_HOST` | Хост Redis | `redis` (в Docker) |
| `VAGUS_SECRET_KEY` | Секрет для JWT | Сгенерировать |
| `VAGUS_ADMIN_USERNAME` | Логин администратора | `admin` |
| `VAGUS_ADMIN_PASSWORD_HASH` | bcrypt-хеш пароля администратора | (секрет) |
| `VAGUS_CONFIG_PATH` | Путь к production-конфигу | `/app/configs/vagus.production.yaml` |

Опционально:

| Переменная | Описание |
|------------|----------|
| `VAGUS_DATABASE_URL` | URL для Alembic (если не задан — собирается из `POSTGRES_*`) |
| `VAGUS_CORS_ORIGINS` | CORS origins (через запятую) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, и др. | Ключи LLM-провайдеров |

Скопируйте `.env.example` в `.env` и заполните значения.

## Database Migrations

### Локально (без Docker)

1. Убедитесь, что PostgreSQL запущен и доступен.
2. Установите переменные окружения:
   ```bash
   export POSTGRES_USER=vagus
   export POSTGRES_PASSWORD=your_password
   export POSTGRES_HOST=localhost
   export POSTGRES_DB=vagus_db
   ```
3. Запустите миграции:
   ```bash
   ./scripts/apply_migrations.sh
   ```
   Или напрямую: `alembic upgrade head`

### В Docker

При запуске `docker-compose -f docker-compose.production.yml up -d` миграции выполняются автоматически через сервис `migrations` перед стартом API.

Для ручного запуска миграций внутри контейнера:

```bash
docker-compose -f docker-compose.production.yml run --rm api alembic upgrade head
```

### Dry-run (проверка без применения)

```bash
alembic upgrade head --sql
alembic downgrade head:base --sql
```

## Docker Deployment

1. Подготовьте `.env`:
   ```bash
   cp .env.example .env
   # Отредактируйте .env — добавьте POSTGRES_PASSWORD, VAGUS_SECRET_KEY, API keys и др.
   ```

2. Запустите stack:
   ```bash
   docker-compose -f docker-compose.production.yml up -d
   ```

3. Проверьте health:
   ```bash
   curl http://localhost/health
   curl http://localhost/health/detailed
   ```

4. Структура сервисов:
   - **nginx** (порт 80) — reverse proxy к API
   - **api** (внутренний 8000) — Vagus Asistent
   - **postgres** (5432) — PostgreSQL 16
   - **redis** (6379) — Redis 7

## Monitoring & Alerting

### Запуск monitoring stack

С production stack:
```bash
docker-compose -f docker-compose.production.yml -f docker-compose.monitoring.yml up -d
```

Отдельно (metrics target: `host.docker.internal:80` или IP хоста):
```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

### Сервисы

| Сервис | Порт | Описание |
|--------|------|----------|
| Prometheus | 9090 | Сбор метрик с Vagus API |
| Grafana | 3000 | Dashboards (admin / GF_ADMIN_PASSWORD) |
| Alertmanager | 9093 | Обработка алертов |

### Метрики Vagus

| Метрика | Описание |
|---------|----------|
| `vagus_active_tasks` | Количество активных задач (pending + in_progress) |
| `vagus_redis_streams_pending` | Pending сообщений в Redis Streams по группам |
| `vagus_redis_streams_dlq_count` | Размер Dead Letter Queue |
| `vagus_health_postgres` | Доступность PostgreSQL (1/0) |
| `vagus_health_redis` | Доступность Redis (1/0) |
| `vagus_postgres_pool_size` | Текущий размер пула соединений PostgreSQL |
| `vagus_synaptic_buffer_size` | Размер буфера SynapticTrainingHandler |
| `vagus_synaptic_events_processed_total` | Обработано событий synaptic |

### Grafana

- URL: http://localhost:3000
- Логин: `admin` (или `GF_ADMIN_USER`)
- Пароль: `GF_ADMIN_PASSWORD` (по умолчанию `admin`)
- Dashboard **Vagus Production Overview**: активные задачи, Redis, PostgreSQL, Synaptic buffer

### Alertmanager и уведомления

Конфиг: `monitoring/alertmanager.yml`

**Telegram**: замените `REPLACE_WITH_TELEGRAM_BOT_TOKEN` и `chat_id: 0` в `monitoring/alertmanager.yml`:
- `bot_token`: токен от @BotFather
- `chat_id`: ID чата (integer, для групп вида `-1001234567890`)

**Slack**: раскомментируйте `slack_configs` в receiver и укажите `api_url` (webhook URL).

### Правила алертов

`monitoring/prometheus_rules.yml`:

| Алерт | Severity | Условие |
|-------|----------|---------|
| VagusAPIDown | critical | API не отвечает 1 мин |
| PostgreSQLUnavailable | critical | `vagus_health_postgres == 0` 2 мин |
| RedisUnavailable | critical | `vagus_health_redis == 0` 2 мин |
| RedisStreamsBacklog | warning | Pending > 1000 или DLQ > 100 |
| PostgresPoolSaturated | warning | Пул соединений на максимуме |

## Backup Procedures

### PostgreSQL

```bash
# Полный дамп
docker exec vagus-postgres pg_dump -U vagus vagus_db > backup_$(date +%Y%m%d).sql

# Восстановление
docker exec -i vagus-postgres psql -U vagus vagus_db < backup_20260221.sql
```

Рекомендуется расписание: ежедневно (например, через cron) в нерабочие часы.

### Redis

Redis сохраняет RDB-снимки в `/data`. При volume `redis_data` данные персистентны. Для ручного snapshot:

```bash
docker exec vagus-redis redis-cli BGSAVE
```

### Ключи и секреты

См. [docs/BACKUP_FORMAT.md](docs/BACKUP_FORMAT.md) и `scripts/backup_keys.py` для бэкапа хранилища API-ключей.

### Хранение бэкапов

- Храните вне контейнеров (внешний том, S3, и т.п.)
- Шифруйте чувствительные дампы
- Рекомендуемый retention: 7–30 дней с ротацией
