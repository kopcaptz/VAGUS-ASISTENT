# Setup Guide

Step-by-step instructions for getting Vagus Asistent running locally.

## Prerequisites

- Python 3.10+
- pip
- Git

## 1. Clone and Install

```bash
git clone https://github.com/kopcaptz/VAGUS-ASISTENT.git
cd VAGUS-ASISTENT
pip install -r requirements.txt
```

## 2. Configure Environment

Copy the example `.env` file and add at least one API key:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# DEEPSEEK_API_KEY=sk-...

# Layer 3: JWT secret (change in production!)
VAGUS_SECRET_KEY=your-secret-key

# Layer 3: Telegram bot (optional)
# TELEGRAM_BOT_TOKEN=123456:ABC...
```

## 3. Configure YAML (Optional)

```bash
cp configs/vagus.yaml.example configs/vagus.yaml
```

Edit `configs/vagus.yaml` to tune cache TTL, budget limits, strategy, etc. See [docs/layer1/CONFIGURATION.md](docs/layer1/CONFIGURATION.md) for all options.

## 4. Verify Installation

Quick smoke test (no API calls):

```bash
PYTHONPATH=src python scripts/verify.py
```

Expected output:

```
Layer 0 — Config & Logging
  [OK]   imports
Layer 1 — LLM Router
  [OK]   imports
Layer 2 — Orchestration
  [OK]   imports
Layer 3 — Interfaces
  [OK]   imports
Smoke tests
  [OK]   CostStrategy
  [OK]   CacheService
  [OK]   CircuitBreaker
...
RESULT: All checks passed.
```

## 5. Run Tests

```bash
# All tests
PYTHONPATH=src pytest tests/ -v

# Layer-specific
PYTHONPATH=src pytest tests/layer1/ -v
PYTHONPATH=src pytest tests/layer2/ -v
PYTHONPATH=src pytest tests/layer3/ -v
```

## 6. Run the API Server

```bash
PYTHONPATH=src uvicorn vagus.layer3.api.main:app --reload --port 8000
```

The API will be available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

## 7. Run the Dashboard (Optional)

```bash
streamlit run dashboard/main.py
```

Opens at http://localhost:8501. Login with `admin` / `admin` (dev credentials).

## 8. Run the CLI (Optional)

```bash
# Login to the API
PYTHONPATH=src python -m vagus login --api-url http://localhost:8000

# Create a task
PYTHONPATH=src python -m vagus task create "What is Python?"

# Check status
PYTHONPATH=src python -m vagus admin status
```

## 9. Run the Telegram Bot (Optional)

Set `TELEGRAM_BOT_TOKEN` in `.env`, then:

```bash
PYTHONPATH=src python -c "
import asyncio
from vagus.layer3.channels.telegram.bot import start_telegram_bot
asyncio.run(start_telegram_bot(api_url='http://localhost:8000', api_key='YOUR_JWT'))
"
```

## Project Structure

```
VAGUS-ASISTENT/
├── configs/vagus.yaml.example   # Full config template
├── .env.example                 # Environment variables template
├── src/vagus/
│   ├── layer0/                  # Config, logging, adapters
│   ├── layer1/                  # LLM Router
│   ├── layer2/                  # Orchestration (agents, memory, skills)
│   └── layer3/                  # Interfaces (API, CLI, bots)
├── dashboard/                   # Streamlit web dashboard
├── tests/                       # Pytest test suite
├── scripts/                     # Verification & functional test scripts
├── examples/                    # Usage examples
└── docs/                        # Architecture & API documentation
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: vagus` | Run with `PYTHONPATH=src` or install in editable mode: `pip install -e .` |
| `bcrypt` / `passlib` errors | Run `pip install "bcrypt==4.1.3"` for compatibility |
| No providers loaded | Set at least one API key in `.env` |
| Tests fail on import | Make sure `pip install -r requirements.txt` completed successfully |
