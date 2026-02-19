# Layer 1 Configuration Reference

All Layer 1 settings live under the `layer1:` key in `configs/vagus.yaml`.

## Full Example

```yaml
layer1:
  router:
    enable_cache: true
    enable_budgeting: true
    enable_monitoring: true
    default_strategy: "hybrid"    # cost | latency | quality | hybrid

  cache:
    ttl_seconds: 3600             # How long cached responses are valid
    max_size_mb: 100              # Maximum in-memory cache size

  budgeting:
    daily_limit_usd: 10.0        # Max daily spend
    monthly_limit_usd: 100.0     # Max monthly spend

  monitoring:
    db_path: "./data/metrics.db"  # SQLite path for metrics
    retention_days: 30            # Auto-delete metrics older than this

  fallback:
    retry_count: 3                # Max retries per request
    backoff_factor: 2.0           # Exponential backoff multiplier
    base_delay_seconds: 1.0      # Initial retry delay
    circuit_breaker_threshold: 5  # Open circuit after N consecutive failures
    providers:                    # Fallback order
      - openai
      - anthropic
      - deepseek
```

## Parameter Reference

### `layer1.router`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_cache` | bool | `true` | Enable response caching |
| `enable_budgeting` | bool | `true` | Enable cost tracking and limits |
| `enable_monitoring` | bool | `true` | Enable request metrics recording |
| `default_strategy` | str | `"hybrid"` | Load-balancing strategy |

### `layer1.cache`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ttl_seconds` | int | `3600` | Cache entry time-to-live |
| `max_size_mb` | int | `100` | Maximum cache size in megabytes |

### `layer1.budgeting`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `daily_limit_usd` | float | `10.0` | Maximum daily spend in USD |
| `monthly_limit_usd` | float | `100.0` | Maximum monthly spend in USD |

### `layer1.monitoring`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | str | `"./data/metrics.db"` | Path to SQLite metrics database |
| `retention_days` | int | `30` | Auto-cleanup threshold |

### `layer1.fallback`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `retry_count` | int | `3` | Maximum retry attempts |
| `backoff_factor` | float | `2.0` | Exponential backoff multiplier |
| `base_delay_seconds` | float | `1.0` | Initial delay before first retry |
| `circuit_breaker_threshold` | int | `5` | Failures before circuit opens |
| `providers` | list | `[openai, anthropic, deepseek]` | Ordered fallback chain |

## Providers Configuration

Provider API keys are loaded from environment variables (`.env` file):

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
GOOGLE_API_KEY=...
```

Provider endpoints and settings are configured in the `providers:` section of the YAML:

```yaml
providers:
  openai:
    endpoint: https://api.openai.com/v1
    rate_limit: 60          # Requests per minute
    timeout: 30             # Seconds
    enabled: true
    models: [gpt-4o, gpt-4o-mini]
  anthropic:
    endpoint: https://api.anthropic.com
    rate_limit: 60
    timeout: 30
    enabled: true
    models: [claude-3-5-sonnet, claude-3-haiku]
```

## Strategy Weights (Hybrid)

The hybrid strategy uses priority-dependent weights:

| Priority | Cost | Latency | Quality |
|----------|------|---------|---------|
| `normal` | 0.33 | 0.33 | 0.34 |
| `urgent` | 0.10 | 0.80 | 0.10 |
| `low` | 0.80 | 0.10 | 0.10 |

## Programmatic Access

Configuration values can be read at runtime via the config adapter:

```python
from vagus.layer0.adapters import config_adapter

ttl = config_adapter.get_int("layer1.cache.ttl_seconds", default=3600)
strategy = config_adapter.get("layer1.router.default_strategy", default="hybrid")
```
