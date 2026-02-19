# Layer 1 API Reference

## LLMRouter

The central entry point for all LLM requests.

### Constructor

```python
from vagus.layer1 import LLMRouter

router = LLMRouter(
    config_manager=None,          # Optional ConfigManager instance
    enable_cache=True,            # Enable response caching
    enable_budgeting=True,        # Enable cost tracking & limits
    enable_monitoring=True,       # Enable metrics recording
    default_strategy="hybrid",    # Balancing strategy: cost | latency | quality | hybrid
    cache_ttl=3600,               # Cache TTL in seconds
    cache_max_mb=100,             # Maximum cache size in MB
    budget_daily=10.0,            # Daily spend limit (USD)
    budget_monthly=200.0,         # Monthly spend limit (USD)
    monitoring_db="metrics.db",   # SQLite path for metrics
    monitoring_retention_days=30, # How long to keep metrics
    fallback_max_retries=3,       # Max retries per request
    fallback_base_delay=1.0,      # Base delay for exponential backoff (seconds)
    fallback_chain=None,          # Provider fallback order, e.g. ["openai", "anthropic"]
)
```

### Initialisation

```python
await router.initialize(providers_config=None)
```

Loads providers from config or auto-discovers available ones by checking for API keys in the environment.

### Sending Requests

```python
async for chunk in router.route_request(
    prompt="Your question here",
    stream=True,           # Stream response chunks
    priority="normal",     # normal | urgent | low (affects strategy weights)
    interactive=False,     # Hint for latency-sensitive routing
    model=None,            # Override model selection
):
    print(chunk.get("content", ""), end="")
```

**Returns:** `AsyncGenerator[Dict[str, Any], None]`

Each chunk contains:
- `content` (str) — text fragment
- `done` (bool) — `True` on the last chunk

### Statistics

```python
stats = router.get_stats()
```

Returns a dict with:
- `requests` — total request count
- `total_cost` — cumulative cost in USD
- `cache` — cache hit/miss stats
- `budgeting` — daily/monthly spend
- `monitoring` — aggregated metrics

---

## Initialisation from Config

```python
from vagus.layer0.config import ConfigManager
from vagus.layer1.integration.config_integration import build_router_kwargs

cm = ConfigManager(config_path="configs/vagus.yaml")
config = cm.load()
kwargs = build_router_kwargs(config)

router = LLMRouter(config_manager=cm, **kwargs)
await router.initialize()
```

---

## CacheService

```python
from vagus.layer1.cache import CacheService

cache = CacheService(ttl_seconds=3600, max_size_mb=100)

await cache.set(key, value, model="gpt-4", priority="normal")
result = await cache.get(key, model="gpt-4", priority="normal")
stats = cache.get_stats()   # {"hits": N, "misses": M, ...}
```

---

## BudgetingService

```python
from vagus.layer1.budgeting import BudgetingService

bs = BudgetingService(daily_limit=10.0, monthly_limit=200.0)

await bs.check_budget(estimated_cost=0.01)  # raises BudgetExceededError
await bs.record_expense(cost=0.005)
stats = bs.get_stats()  # {"daily_spent": ..., "monthly_spent": ...}
```

---

## MonitoringService

```python
from vagus.layer1.monitoring import MonitoringService

ms = MonitoringService(db_path="metrics.db", retention_days=30)

ms.record_complete_request(
    trace_id="abc123",
    provider="openai",
    model="gpt-4o-mini",
    success=True,
    e2e_ms=450.0,
    cost_usd=0.002,
)
stats = ms.get_stats()
```

---

## CircuitBreaker

```python
from vagus.layer1.fallback import CircuitBreaker

cb = CircuitBreaker(
    failure_threshold=5,       # Open after 5 consecutive failures
    recovery_timeout=60,       # Try again after 60 seconds
)

result = await cb.call(async_function)
```

States: `CLOSED` (normal) → `OPEN` (failing) → `HALF_OPEN` (testing recovery)

---

## Balancing Strategies

```python
from vagus.layer1.balancing import CostStrategy, HybridStrategy

strategy = HybridStrategy()
provider_id = strategy.select_provider(
    providers={
        "openai": {"cost": 0.01, "latency": 100, "quality": 0.9},
        "anthropic": {"cost": 0.02, "latency": 80, "quality": 0.95},
    },
    context={"priority": "normal", "interactive": False},
)
```
