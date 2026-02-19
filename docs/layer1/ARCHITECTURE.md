# Layer 1 Architecture — LLM Router

## Overview

Layer 1 is the LLM routing core of Vagus Asistent. Every LLM call in the system — whether from an agent, the API, or the CLI — passes through `LLMRouter`, which provides caching, budgeting, monitoring, load-balancing and fault tolerance in a single unified pipeline.

## Component Diagram

```
                          ┌──────────────────┐
                          │   LLMRouter      │ ◄── Single entry point
                          │   (facade)       │
                          └────────┬─────────┘
                                   │
           ┌───────────────────────┼───────────────────────┐
           │                       │                       │
     ┌─────▼─────┐         ┌──────▼──────┐         ┌──────▼──────┐
     │  Cache     │         │  Budgeting  │         │  Monitoring │
     │  Service   │         │  Service    │         │  Service    │
     └─────┬─────┘         └──────┬──────┘         └──────┬──────┘
           │                      │                       │
           └──────────────────────┼───────────────────────┘
                                  │
                          ┌───────▼───────┐
                          │   Strategy    │
                          │   Manager     │
                          │ (cost/latency │
                          │  /quality/    │
                          │   hybrid)     │
                          └───────┬───────┘
                                  │
                          ┌───────▼───────┐
                          │   Fallback    │
                          │   Handler     │
                          │ + Circuit     │
                          │   Breaker     │
                          └───────┬───────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
        ┌─────▼─────┐     ┌──────▼─────┐     ┌───────▼────┐
        │  OpenAI    │     │ Anthropic  │     │  DeepSeek  │
        │  Provider  │     │  Provider  │     │  Provider  │
        └────────────┘     └────────────┘     └────────────┘
```

## Components

### 1. LLMRouter (`router/llm_router.py`)

The facade that orchestrates the full request pipeline:

1. **Cache check** — return cached result if available
2. **Budget check** — reject if daily/monthly limit exceeded
3. **Strategy selection** — pick the best provider
4. **Fallback execution** — retry with fallback providers on failure
5. **Post-processing** — record metrics, update cache, track cost

### 2. Providers (`providers/`)

| Provider | Module | Models |
|----------|--------|--------|
| OpenAI | `openai_provider.py` | gpt-4o, gpt-4o-mini |
| Anthropic | `anthropic_provider.py` | claude-3-5-sonnet, claude-3-haiku |
| DeepSeek | `deepseek_provider.py` | deepseek-chat |
| OpenRouter | `openrouter_provider.py` | Any model via OpenRouter |
| Google | `google_provider.py` | gemini-pro |

All providers inherit from `BaseProvider` and implement:
- `request(prompt, stream, model, ...)` — async generator
- `is_available()` — checks if the provider has a valid API key
- `calculate_cost(input_tokens, output_tokens)` — cost estimation

### 3. Balancing Strategies (`balancing/`)

| Strategy | Selection criterion |
|----------|-------------------|
| `CostStrategy` | Cheapest provider |
| `LatencyStrategy` | Fastest provider |
| `QualityStrategy` | Highest-quality provider |
| `HybridStrategy` | Weighted combination (configurable per priority) |

`StrategyManager` selects the active strategy and provides it to the router.

### 4. Fallback System (`fallback/`)

- **FallbackHandler** — executes requests with retry logic and provider rotation
- **CircuitBreaker** — opens after N consecutive failures, auto-resets after a timeout
- **FallbackChain** — ordered list of fallback providers

### 5. Cache (`cache/`)

In-memory cache with configurable TTL and max size. Cache keys are derived from the prompt + model + priority.

### 6. Budgeting (`budgeting/`)

Tracks daily and monthly spend. Raises `BudgetExceededError` when limits are hit.

### 7. Monitoring (`monitoring/`)

Records every request in SQLite: provider, model, latency, cost, success/failure. Supports retention-based cleanup.

## Request Flow

```
User prompt
    │
    ▼
LLMRouter.route_request()
    │
    ├─► Cache HIT? → return cached
    │
    ├─► Budget OK? → continue / raise BudgetExceededError
    │
    ├─► Strategy selects provider
    │
    ├─► FallbackHandler.execute()
    │     ├─► Provider 1 → success → return
    │     ├─► Provider 1 → fail → CircuitBreaker records failure
    │     ├─► Provider 2 → success → return
    │     └─► ... up to N retries
    │
    ├─► Record metrics (MonitoringService)
    ├─► Update cache
    └─► Track cost (BudgetingService)
```

## Integration with Layer 0

Layer 1 reads configuration from Layer 0 via `config_integration.py`:

```python
from vagus.layer1.integration.config_integration import build_router_kwargs
kwargs = build_router_kwargs(config)
router = LLMRouter(**kwargs)
```

This maps YAML keys like `layer1.cache.ttl_seconds` to constructor arguments.
