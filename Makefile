.PHONY: help build run stop restart logs test test-unit test-layer3 test-cov \
       lint format clean deploy dev db-migrate db-reset certs status

COMPOSE = docker compose
PYTEST  = python3 -m pytest

# ── Help ─────────────────────────────────────────────────────────────────
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ── Build ────────────────────────────────────────────────────────────────
build: ## Build all Docker images
	$(COMPOSE) build

build-no-cache: ## Build without Docker cache
	$(COMPOSE) build --no-cache

# ── Run ──────────────────────────────────────────────────────────────────
run: ## Start all services in background
	$(COMPOSE) up -d

dev: ## Start core services only (api + redis + postgres)
	$(COMPOSE) up -d api redis postgres

run-fg: ## Start all services in foreground
	$(COMPOSE) up

stop: ## Stop all services
	$(COMPOSE) down

restart: ## Restart all services
	$(COMPOSE) down && $(COMPOSE) up -d

# ── Logs ─────────────────────────────────────────────────────────────────
logs: ## Tail logs from all services
	$(COMPOSE) logs -f --tail=100

logs-api: ## Tail API logs only
	$(COMPOSE) logs -f --tail=100 api

# ── Testing ──────────────────────────────────────────────────────────────
test: ## Run all tests
	PYTHONPATH=src $(PYTEST) tests/ -v

test-unit: ## Run unit tests only
	PYTHONPATH=src $(PYTEST) tests/layer1/unit/ tests/layer2/ tests/layer3/ -v

test-layer3: ## Run Layer 3 API/Auth/WS/CLI/Dashboard tests
	PYTHONPATH=src $(PYTEST) tests/layer3/ -v

test-cov: ## Run tests with coverage report
	PYTHONPATH=src $(PYTEST) tests/ -v --cov=src/vagus --cov-report=term-missing --cov-report=html

# ── Linting ──────────────────────────────────────────────────────────────
lint: ## Run linters (ruff)
	ruff check src/ tests/

format: ## Auto-format code
	ruff format src/ tests/

# ── Database ─────────────────────────────────────────────────────────────
db-migrate: ## Run database migrations
	$(COMPOSE) exec api python -m vagus.layer3.db.migrate

db-reset: ## Reset database (WARNING: destructive)
	$(COMPOSE) down -v postgres
	$(COMPOSE) up -d postgres
	@echo "Waiting for PostgreSQL..." && sleep 3
	$(MAKE) db-migrate

# ── SSL Certificates ────────────────────────────────────────────────────
certs: ## Generate self-signed SSL certs for development
	mkdir -p certs
	openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
		-keyout certs/server.key -out certs/server.crt \
		-subj "/C=RU/ST=Moscow/L=Moscow/O=Vagus/CN=localhost"
	@echo "Self-signed certificates created in certs/"

# ── Deploy ───────────────────────────────────────────────────────────────
deploy: ## Full production deploy (build + run + migrate)
	$(MAKE) build
	$(MAKE) run
	@echo "Waiting for services to start..." && sleep 5
	@echo "Vagus Asistent is running!"
	@echo "  API:        http://localhost:$${API_PORT:-8000}"
	@echo "  Dashboard:  http://localhost:$${STREAMLIT_PORT:-8501}"
	@echo "  Grafana:    http://localhost:$${GRAFANA_PORT:-3000}"
	@echo "  Prometheus: http://localhost:$${PROMETHEUS_PORT:-9090}"

# ── Cleanup ──────────────────────────────────────────────────────────────
clean: ## Remove containers, volumes, and build artifacts
	$(COMPOSE) down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage dist build *.egg-info

status: ## Show service status
	$(COMPOSE) ps
