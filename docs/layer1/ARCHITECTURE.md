# Архитектура Слоя 1

## Компоненты

### 1. Роутер (router/)
- LLMRouter - фасад системы
- RouterManager - управление роутером

### 2. Провайдеры (providers/)
- BaseProvider - абстрактный класс
- Конкретные провайдеры: OpenAI, Anthropic, DeepSeek, OpenRouter

### 3. Стратегии балансировки (balancing/)
- BaseBalancingStrategy - абстрактный класс
- HybridStrategy - основная стратегия

### 4. Fallback система (fallback/)
- CircuitBreaker - паттерн Circuit Breaker
- FallbackHandler - управление fallback цепочками

### 5. Мониторинг (monitoring/)
- MonitoringService - сбор метрик
- SQLite хранилище

### 6. Кэширование (cache/)
- CacheService - in-memory кэш с TTL

### 7. Бюджетирование (budgeting/)
- BudgetingService - контроль лимитов расходов

### 8. Интеграция (integration/)
- Интеграция с Слоем 0 (конфигурация, логирование)