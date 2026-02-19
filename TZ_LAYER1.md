# ТЕХНИЧЕСКОЕ ЗАДАНИЕ: СЛОЙ 1 - ЯДРО LLM

## 📋 ОБЩАЯ ИНФОРМАЦИЯ
- **Проект:** Vagus Asistent
- **Слой:** 1 (Ядро LLM)
- **Статус:** В разработке
- **Архитектура:** На основе Manus AI
- **Срок:** 6 дней

## 🎯 ЦЕЛЬ
Создать мульти-модельный роутер LLM с балансировкой нагрузки, fallback системой, кэшированием и мониторингом.

## 🏗 АРХИТЕКТУРА (9 КОМПОНЕНТОВ)

### 1. LLMRouter (фасад)
- **Файл:** `src/vagus/layer1/router/llm_router.py`
- **Назначение:** Центральная точка входа, координация всех компонентов
- **Требования:**
  - Поддержка streaming и non-streaming запросов
  - Интеграция со всеми сервисами
  - Горячая перезагрузка конфигурации
  - Статистика и мониторинг

### 2. Провайдеры LLM
- **Папка:** `src/vagus/layer1/providers/`
- **Базовый класс:** `BaseProvider` (abstract)
- **Конкретные провайдеры:**
  - `OpenAIProvider` - GPT-4o, GPT-4o-mini, o1
  - `AnthropicProvider` - Claude 3.5 Sonnet, Haiku
  - `DeepSeekProvider` - DeepSeek Chat
  - `OpenRouterProvider` - Агрегатор моделей
  - `GoogleProvider` - Gemini (опционально)
- **Требования:**
  - Наследование от BaseProvider
  - Поддержка streaming
  - Расчёт стоимости запросов
  - Обработка ошибок API

### 3. Стратегии балансировки
- **Папка:** `src/vagus/layer1/balancing/`
- **Базовый класс:** `BaseBalancingStrategy` (abstract)
- **Конкретные стратегии:**
  - `CostStrategy` - выбор по минимальной стоимости
  - `LatencyStrategy` - выбор по минимальной задержке
  - `QualityStrategy` - выбор по максимальному качеству
  - `HybridStrategy` - гибридная стратегия (основная)
- **Алгоритм HybridStrategy:**
  ```
  1. Сбор метрик: стоимость, задержка, качество
  2. Нормализация к [0, 1] (инверсия для стоимости/задержки)
  3. Взвешивание по типу запроса:
     - urgent/interactive: cost=0.1, latency=0.8, quality=0.1
     - normal: cost=0.33, latency=0.33, quality=0.34
     - low/background: cost=0.8, latency=0.1, quality=0.1
  4. Выбор провайдера с максимальной оценкой
  ```

### 4. Fallback система
- **Папка:** `src/vagus/layer1/fallback/`
- **Компоненты:**
  - `CircuitBreaker` - паттерн Circuit Breaker (CLOSED/OPEN/HALF_OPEN)
  - `FallbackHandler` - управление цепочками fallback
  - `FallbackChain` - конфигурация цепочек
  - `RetryManager` - exponential backoff (1s → 2s → 4s → 8s)
- **Требования:**
  - Автоматическое переключение при ошибках
  - Защита от лавины запросов
  - Восстановление после сбоев

### 5. Мониторинг
- **Папка:** `src/vagus/layer1/monitoring/`
- **Компоненты:**
  - `MonitoringService` - основной сервис
  - `MetricsCollector` - сбор метрик
  - `LatencyTracker` - TTFT и E2E latency
  - `CostTracker` - расчёт стоимости
  - `QualityMonitor` - оценка качества
  - `MetricsStorage` - SQLite хранилище
- **Метрики:**
  - `trace_id` - уникальный ID запроса
  - `provider`, `model` - использованные ресурсы
  - `ttft_ms`, `e2e_ms` - задержки
  - `cost_usd` - стоимость
  - `success`, `error_type` - статус выполнения

### 6. Кэширование
- **Папка:** `src/vagus/layer1/cache/`
- **Компоненты:**
  - `CacheService` - in-memory кэш с TTL
  - `CacheKeyGenerator` - SHA-256 ключи
  - `CacheStats` - статистика кэша
- **Параметры:**
  - TTL: 1 час (по умолчанию)
  - Максимальный размер: 100 MB
  - Автоочистка устаревших записей

### 7. Бюджетирование
- **Папка:** `src/vagus/layer1/budgeting/`
- **Компоненты:**
  - `BudgetingService` - основной сервис
  - `BudgetLimits` - лимиты расходов
  - `ExpenseTracker` - трекер расходов
- **Лимиты:**
  - Дневной: $10.00 (по умолчанию)
  - Месячный: $200.00 (по умолчанию)
  - Исключение: `BudgetExceededError`

### 8. Интеграция
- **Папка:** `src/vagus/layer1/integration/`
- **Компоненты:**
  - `ConfigIntegration` - интеграция с Слоем 0 (конфигурация)
  - `LoggingIntegration` - интеграция с логированием
  - `HotReloadIntegration` - горячая перезагрузка

### 9. Фабрики и реестры
- **Файлы:**
  - `provider_factory.py` - фабрика провайдеров
  - `provider_registry.py` - реестр провайдеров (плагинная система)
  - `strategy_manager.py` - менеджер стратегий

## 📁 СТРУКТУРА ПРОЕКТА
```
Vagus_Asistent/src/vagus/layer1/
├── router/                    # Роутер LLM
│   ├── llm_router.py         # Основной роутер (фасад)
│   ├── router_manager.py     # Менеджер роутера
│   ├── request_handler.py    # Обработчик запросов
│   └── response_builder.py   # Построитель ответов
├── providers/                # Провайдеры LLM
│   ├── base_provider.py      # Базовый класс
│   ├── openai_provider.py    # OpenAI API
│   ├── anthropic_provider.py # Anthropic API
│   ├── deepseek_provider.py  # DeepSeek API
│   ├── openrouter_provider.py # OpenRouter API
│   ├── google_provider.py    # Google Gemini API
│   ├── provider_factory.py   # Фабрика провайдеров
│   └── provider_registry.py  # Реестр провайдеров
├── balancing/                # Стратегии балансировки
│   ├── base_strategy.py      # Базовый класс
│   ├── cost_strategy.py      # Стратегия по стоимости
│   ├── latency_strategy.py   # Стратегия по задержке
│   ├── quality_strategy.py   # Стратегия по качеству
│   ├── hybrid_strategy.py    # Гибридная стратегия
│   └── strategy_manager.py   # Менеджер стратегий
├── fallback/                 # Fallback система
│   ├── circuit_breaker.py    # Circuit Breaker
│   ├── fallback_handler.py   # Fallback Handler
│   ├── fallback_chain.py     # Цепочки fallback
│   └── retry_manager.py      # Менеджер повторных попыток
├── monitoring/               # Мониторинг
│   ├── monitoring_service.py # Основной сервис
│   ├── metrics_collector.py  # Сборщик метрик
│   ├── latency_tracker.py    # Трекер задержек
│   ├── cost_tracker.py       # Трекер стоимости
│   ├── quality_monitor.py    # Монитор качества
│   └── metrics_storage.py    # Хранилище метрик (SQLite)
├── cache/                    # Кэширование
│   ├── cache_service.py      # Сервис кэширования
│   ├── cache_key_generator.py # Генератор ключей
│   └── cache_stats.py        # Статистика кэша
├── budgeting/                # Бюджетирование
│   ├── budgeting_service.py  # Сервис бюджетирования
│   ├── budget_limits.py      # Лимиты расходов
│   └── expense_tracker.py    # Трекер расходов
└── integration/              # Интеграция
    ├── config_integration.py # Интеграция с конфигурацией
    ├── logging_integration.py # Интеграция с логированием
    └── hot_reload_integration.py # Горячая перезагрузка
```

## 🔧 ЖИЗНЕННЫЙ ЦИКЛ ЗАПРОСА
```
1. Проверка кэша → если есть, возврат
2. Проверка бюджета → если превышен, ошибка
3. Выбор провайдера (стратегия балансировки)
4. Выполнение с fallback (circuit breaker + exponential backoff)
5. Сохранение в кэш (если успешно)
6. Запись метрик (мониторинг)
7. Обновление бюджета
```

## ⚙️ КОНФИГУРАЦИЯ (дополнение к vagus.yaml)
```yaml
layer1:
  router:
    enable_cache: true
    enable_budgeting: true
    enable_monitoring: true
    default_strategy: "hybrid"
    
  cache:
    ttl_seconds: 3600
    max_size_mb: 100
    
  budgeting:
    daily_limit_usd: 10.0
    monthly_limit_usd: 200.0
    data_dir: "./data/budgeting"
    
  monitoring:
    db_path: "metrics.db"
    retention_days: 30
    
  fallback:
    max_retries: 3
    base_delay_seconds: 1.0
    circuit_breaker:
      failure_threshold: 5
      recovery_timeout_seconds: 60
      half_open_max_requests: 3
      
  strategies:
    hybrid:
      weights:
        normal: {cost: 0.33, latency: 0.33, quality: 0.34}
        urgent: {cost: 0.10, latency: 0.80, quality: 0.10}
        low: {cost: 0.80, latency: 0.10, quality: 0.10}
```

## 🚀 API ИНТЕРФЕЙС
```python
# Инициализация
from vagus.layer0 import ConfigManager
from vagus.layer1 import LLMRouter

config_manager = ConfigManager()
router = LLMRouter(config_manager)
await router.initialize()

# Базовый запрос
async for chunk in router.route_request(
    prompt="Привет, как дела?",
    stream=True,
    priority="normal",
    interactive=False
):
    print(chunk.get("content", ""), end="")

# Получение статистики
stats = router.get_stats()
print(f"Использовано провайдеров: {stats['providers_used']}")
print(f"Общая стоимость: ${stats['total_cost']:.2f}")
```

## 🧪 ТЕСТИРОВАНИЕ
### Unit-тесты:
- Circuit Breaker: переходы состояний
- Cache: попадания/промахи, TTL
- Budgeting: лимиты, исключения
- Strategies: выбор провайдера

### Интеграционные тесты:
- Полный цикл запроса
- Fallback цепочка
- Hot-reload конфигурации
- Запись метрик в SQLite

### Нагрузочные тесты:
- Максимальный RPS
- Поведение при сбоях провайдеров
- Утечки памяти

## 📅 ПЛАН РЕАЛИЗАЦИИ (6 ДНЕЙ)

### День 1-2: Базовые сервисы ✅
- [x] CacheService - кэширование с TTL
- [x] BudgetingService - лимиты расходов
- [x] CircuitBreaker - паттерн Circuit Breaker
- [ ] MonitoringService - SQLite + метрики
- [ ] FallbackHandler - exponential backoff

### День 3-4: Провайдеры и стратегии
- [ ] BaseProvider - абстрактный класс
- [ ] OpenAIProvider, AnthropicProvider
- [ ] HybridStrategy - балансировка
- [ ] ProviderFactory, ProviderRegistry

### День 5: Роутер и интеграция
- [ ] LLMRouter - фасад системы
- [ ] Интеграция с Слоем 0
- [ ] Hot-reload конфигурации
- [ ] Базовые тесты

### День 6: Тестирование и документация
- [ ] Unit-тесты всех компонентов
- [ ] Интеграционные тесты
- [ ] Демо-примеры
- [ ] Документация API

## 🎯 КРИТЕРИИ ПРИЕМКИ
### Функциональные:
1. ✅ Поддержка минимум 3 провайдеров
2. ✅ Работающий fallback с circuit breaker
3. ✅ Кэширование с TTL
4. ✅ Бюджетирование с лимитами
5. ✅ Мониторинг в SQLite
6. ✅ Гибридная стратегия балансировки
7. ✅ Hot-reload конфигурации
8. ✅ Streaming ответов

### Нефункциональные:
1. ⏱️ Latency: TTFT < 2s для 95% запросов
2. 💰 Стоимость: Автоматический выбор дешёвых моделей
3. 🛡️ Надёжность: 99.9% uptime при сбоях провайдера
4. 📊 Мониторинг: Полная трассировка запросов
5. 🔧 Расширяемость: Легкое добавление новых провайдеров

## 📚 ДОКУМЕНТАЦИЯ
- `docs/layer1/ARCHITECTURE.md` - архитектура
- `docs/layer1/API_REFERENCE.md` - API справочник
- `docs/layer1/CONFIGURATION.md` - конфигурация
- `examples/layer1/` - примеры использования

## 🔗 ИНТЕГРАЦИЯ
- **Слой 0:** Конфигурация, логирование, безопасность (✅ готов)
- **Слой 2:** Агентная система (📅 планируется)
- **Слой 3:** Интерфейсы (📅 планируется)
- **Слой 4:** Интеграции (📅 планируется)

---

**СТАТУС:** Структура создана, базовые компоненты реализованы. Готово к разработке остальных компонентов.