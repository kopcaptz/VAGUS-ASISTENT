.PHONY: help install run test lint docker-build docker-up docker-down clean

PYTHON ?= python3
PYTHONPATH ?= src

help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	$(PYTHON) -m pip install -r requirements.txt

run: ## Run REST API server (uvicorn)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m uvicorn vagus.layer3.api.main:app --host 0.0.0.0 --port 8000 --reload

run-dashboard: ## Run Streamlit dashboard
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m streamlit run dashboard/main.py --server.port 8501

run-telegram: ## Run Telegram bot
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -c "import asyncio; from vagus.layer3.channels.telegram.bot import start_telegram_bot; asyncio.run(start_telegram_bot())"

test: ## Run all tests
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/ -v

test-layer1: ## Run Layer 1 tests only
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/layer1/ -v

test-layer2: ## Run Layer 2 tests only
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/layer2/ -v

test-layer3: ## Run Layer 3 tests only
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/layer3/ -v

test-coverage: ## Run tests with coverage
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m pytest tests/ -v --cov=vagus --cov-report=term-missing

verify: ## Run quick verification
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) scripts/verify.py

lint: ## Run linting (ruff)
	$(PYTHON) -m ruff check src/ tests/

docker-build: ## Build Docker image
	docker build -t vagus-asistent .

docker-up: ## Start all services via Docker Compose
	docker compose up -d

docker-down: ## Stop all services
	docker compose down

clean: ## Clean generated files
	rm -rf __pycache__ .pytest_cache .ruff_cache metrics.db data/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
