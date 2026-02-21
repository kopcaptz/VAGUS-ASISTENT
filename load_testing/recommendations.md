# Рекомендации по настройке на основе нагрузочного тестирования

Результаты нагрузочных тестов (parallel_tasks, redis_streams_latency, postgres_pool_performance) следует использовать для оптимизации конфигурации.

## Пул PostgreSQL

| Проблема | Рекомендация |
|----------|--------------|
| Pool exhaustion (ошибки при высокой нагрузке) | Увеличить `max_size` в ArtifactKnowledgeBasePG (по умолчанию 10) до 20–50 |
| Высокая latency p99 | Проверить индексы на таблицах artifacts, artifact_relationships; увеличить `max_size` при конкуренции за соединения |
| Deadlocks | Уменьшить concurrency при записи; обеспечить порядок блокировок в транзакциях |

Конфигурация: `layer2.knowledge_base.postgres_url` и параметры пула при создании ArtifactKnowledgeBasePG.

## Redis Streams

| Проблема | Рекомендация |
|----------|--------------|
| Высокая publish latency | Проверить `maxlen` потока; при approximate=True и большом maxlen — возможна задержка; убедиться, что Redis не перегружен |
| Большой stream_length | Уменьшить maxlen или настроить периодическую очистку (XTRIM) |
| Рост DLQ | Увеличить max_retries в process_events; проверить handler на ошибки |

Конфигурация: `layer2.communication.redis_url`, `event_bus.use_streams`, `stream_name`.

## Synaptic buffer (SynapticTrainingHandler)

| Проблема | Рекомендация |
|----------|--------------|
| buffer_size часто на верхней границе | Увеличить `buffer_size` (по умолчанию 50) для снижения частоты flush |
| Низкий throughput quality_gate | Уменьшить `buffer_timeout_ms` (по умолчанию 100) для более частого flush при низкой нагрузке |
| Смешанная нагрузка | Гибрид: flush при `count >= buffer_size` ИЛИ `time >= buffer_timeout_ms` (см. [buffering_recommendation.md](../docs/buffering_recommendation.md)) |

Конфигурация: параметры при создании SynapticTrainingHandler (через layer2 при использовании MasterOrchestrator).

## Параллельные задачи (API)

| Проблема | Рекомендация |
|----------|--------------|
| Много ошибок при 100+ задачах | Проверить rate limits: `security.rate_limit.user_requests_per_minute`; таймауты агентов в task_timeouts |
| Долгое время выполнения | Увеличить таймауты researcher/coder; проверить LLM провайдеры (rate limits, latency) |
| Timeout при poll | Увеличить poll_interval в parallel_tasks; проверить нагрузку на API |

## Запуск тестов

```bash
# API должен быть запущен (uvicorn)
python -m load_testing.parallel_tasks --url http://localhost:8000 --tasks 100
python -m load_testing.redis_streams_latency --redis-url redis://localhost:6379/0
python -m load_testing.postgres_pool_performance --num-requests 1000 --concurrency 50

# Все тесты последовательно
python -m load_testing.run_all --url http://localhost:8000
```

Отчёты сохраняются в `load_testing/reports/`.
