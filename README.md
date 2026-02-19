# Vagus Asistent

Multi-layer AI agent system with LLM routing, orchestration and interfaces.

## Architecture

| Layer | Purpose | Technology |
|-------|---------|-----------|
| **Layer 0** | Configuration, logging, adapters | Pydantic, YAML, dotenv |
| **Layer 1** | LLM Router — multi-provider routing | Cache, budgeting, monitoring, fallback |
| **Layer 2** | Orchestration — agents, memory, skills | Orchestrator-Worker pattern, asyncio |
| **Layer 3** | Interfaces — API, CLI, dashboard, bots | FastAPI, Typer, Streamlit, aiogram |

## Quick Start

```bash
# 1. Install
git clone https://github.com/kopcaptz/VAGUS-ASISTENT.git
cd VAGUS-ASISTENT
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — add at least one API key (OPENAI_API_KEY, etc.)

# 3. Verify
PYTHONPATH=src python scripts/verify.py

# 4. Run the API server
PYTHONPATH=src uvicorn vagus.layer3.api.main:app --reload --port 8000

# 5. Open docs
# Swagger UI:  http://localhost:8000/docs
# Health:      http://localhost:8000/health
```

## Usage

### Python API

```python
import asyncio
from vagus.layer1 import LLMRouter

async def main():
    router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        fallback_chain=["openai", "anthropic", "deepseek"],
    )
    await router.initialize()

    async for chunk in router.route_request("Hello!", stream=True):
        print(chunk.get("content", ""), end="")

asyncio.run(main())
```

### REST API

```bash
# Get a token
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin&password=admin"

# Create a task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?", "task_type": "research"}'

# Check status
curl http://localhost:8000/api/v1/tasks/<task_id> \
  -H "Authorization: Bearer <token>"
```

### CLI

```bash
PYTHONPATH=src python -m vagus login
PYTHONPATH=src python -m vagus task create "Explain asyncio"
PYTHONPATH=src python -m vagus task list
PYTHONPATH=src python -m vagus admin status
```

### Web Dashboard

```bash
streamlit run dashboard/main.py
# Opens at http://localhost:8501
```

## Testing

```bash
# All tests (136+)
PYTHONPATH=src pytest tests/ -v

# By layer
PYTHONPATH=src pytest tests/layer1/ -v
PYTHONPATH=src pytest tests/layer2/ -v
PYTHONPATH=src pytest tests/layer3/ -v
PYTHONPATH=src pytest tests/layer0/ -v

# Quick scripts
PYTHONPATH=src python scripts/verify.py
PYTHONPATH=src python scripts/run_quick_tests.py
PYTHONPATH=src python scripts/test_functional.py
```

## Project Structure

```
VAGUS-ASISTENT/
├── README.md
├── SETUP.md                         # Step-by-step setup guide
├── .env.example                     # Environment variables template
├── requirements.txt
├── configs/
│   └── vagus.yaml.example           # Full YAML configuration template
├── examples/
│   └── layer1/basic_usage.py        # LLMRouter usage demo
├── scripts/
│   ├── verify.py                    # Quick import & smoke test
│   ├── test_functional.py           # Full functional test suite
│   └── run_quick_tests.py           # Lightweight dev tests
├── src/vagus/
│   ├── __init__.py
│   ├── __main__.py                  # python -m vagus → CLI
│   ├── layer0/                      # Configuration & logging
│   │   ├── config/
│   │   │   ├── config_manager.py    # YAML + env loading, hot-reload, get/set
│   │   │   └── models.py           # Pydantic models (AppConfig, Layer1Config, ...)
│   │   ├── logging/                 # Unified logger
│   │   └── adapters/                # Config adapter with env fallback
│   ├── layer1/                      # LLM Router
│   │   ├── router/llm_router.py     # Central routing facade
│   │   ├── providers/               # OpenAI, Anthropic, DeepSeek, ...
│   │   ├── balancing/               # Cost, latency, quality, hybrid strategies
│   │   ├── fallback/                # Circuit breaker, retry, fallback chain
│   │   ├── cache/                   # In-memory cache with TTL
│   │   ├── budgeting/               # Daily/monthly spend tracking
│   │   ├── monitoring/              # SQLite metrics storage
│   │   └── integration/             # Layer 0 config integration
│   ├── layer2/                      # Orchestration
│   │   ├── orchestrator.py          # TaskOrchestrator (state machine)
│   │   ├── agents/                  # Researcher, Coder, Analyst
│   │   ├── memory/                  # Episodic + Semantic memory
│   │   ├── skills/                  # Skill registry (search, code, file)
│   │   └── communication/           # Pub/sub message bus
│   └── layer3/                      # Interfaces
│       ├── api/                     # FastAPI REST API + WebSocket
│       │   ├── main.py
│       │   ├── models.py
│       │   ├── auth.py              # JWT authentication
│       │   ├── dependencies.py
│       │   ├── middleware/          # Rate limiting, request logging
│       │   └── routers/             # tasks, agents, status, auth
│       ├── cli/                     # Typer CLI
│       │   ├── app.py
│       │   ├── commands/            # task, agent, admin
│       │   └── utils/               # config, api_client, output
│       └── channels/                # Chat bot gateway
│           ├── gateway.py
│           ├── telegram/            # aiogram 3.x bot
│           └── discord/             # Placeholder
├── dashboard/                       # Streamlit web dashboard
│   ├── main.py
│   ├── pages/                       # Tasks, Monitoring, Agents, Settings
│   └── utils/                       # API client, auth, charts
├── tests/
│   ├── layer0/                      # Config models, adapter, get/set tests
│   ├── layer1/                      # Unit + integration tests
│   ├── layer2/                      # Agent, memory, orchestrator tests
│   └── layer3/                      # REST API endpoint tests
└── docs/
    ├── layer1/
    │   ├── ARCHITECTURE.md          # Component diagram & request flow
    │   ├── API_REFERENCE.md         # LLMRouter, CacheService, etc.
    │   └── CONFIGURATION.md         # YAML parameter reference
    ├── LAYER2_PLAN.md               # Layer 2 design document
    └── LAYER3_DESIGN.md             # Layer 3 design document
```

## Documentation

- [SETUP.md](SETUP.md) — Installation and first-run guide
- [docs/layer1/ARCHITECTURE.md](docs/layer1/ARCHITECTURE.md) — Layer 1 component architecture
- [docs/layer1/API_REFERENCE.md](docs/layer1/API_REFERENCE.md) — LLMRouter API reference
- [docs/layer1/CONFIGURATION.md](docs/layer1/CONFIGURATION.md) — YAML configuration reference
- [docs/LAYER2_PLAN.md](docs/LAYER2_PLAN.md) — Layer 2 design (Manus AI)
- [docs/LAYER3_DESIGN.md](docs/LAYER3_DESIGN.md) — Layer 3 design (Manus AI)

## Requirements

- Python 3.10+
- See [requirements.txt](requirements.txt) for full dependency list

## License

MIT
