# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Vagus Asistent is a multi-layer AI agent system with an LLM router (Python 3.12+, FastAPI, Streamlit). See `README.md` for full architecture and commands.

### Running services

**FastAPI REST API** (port 8000):
```bash
set -a && source .env && set +a
PYTHONPATH=src python3 -m uvicorn vagus.layer3.api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Streamlit Dashboard** (port 8501):
```bash
PYTHONPATH=src python3 -m streamlit run dashboard/main.py --server.port 8501 --server.headless true
```

### Gotchas

- The `.env` file contains bcrypt hashes with `$` characters. You **must not** use `source .env` without `set -a` / `set +a`, and bcrypt hashes must be single-quoted when exported manually (e.g., `export VAGUS_ADMIN_PASSWORD_HASH='$2b$12$...'`). Bash will interpolate `$` in double quotes.
- `VAGUS_SECRET_KEY` must be set as an environment variable before the app can import; the module-level check in `src/vagus/layer3/api/auth.py` raises `ValueError` at import time if missing.
- Standard commands: `make run`, `make test`, `make lint`, `make run-dashboard` (see `Makefile`).
- Lint uses `ruff` (`pip install ruff` if not in `requirements.txt`).
- Tests: `PYTHONPATH=src pytest tests/ -v`. Markers `e2e` and `chaos` require real LLM keys and Docker respectively.
- Redis and PostgreSQL are optional for local dev; the app falls back to SQLite and in-memory alternatives.
- No pre-commit hooks or git hooks are configured.
