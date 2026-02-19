# Конфигурация Слоя 1

## Пример конфигурации (дополнение к vagus.yaml)
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
    
  monitoring:
    db_path: "metrics.db"
    retention_days: 30
    
  fallback:
    max_retries: 3
    base_delay_seconds: 1.0
    circuit_breaker:
      failure_threshold: 5
      recovery_timeout_seconds: 60
      
  strategies:
    hybrid:
      weights:
        normal: {cost: 0.33, latency: 0.33, quality: 0.34}
        urgent: {cost: 0.10, latency: 0.80, quality: 0.10}
        low: {cost: 0.80, latency: 0.10, quality: 0.10}
```