.PHONY: help \
        venv install install-backend install-frontend install-clean install-all dev reset \
        test test-all lint format typecheck verify \
        migrate migrate-down migrate-rev \
        start start-backend start-frontend start-deps start-all _wait-backend \
        stop stop-backend stop-frontend stop-deps stop-all \
        status logs logs-api logs-worker logs-frontend \
        run-api run-worker \
        docker-build docker-up docker-down docker-logs \
        frontend-install frontend-dev frontend-build frontend-lint frontend-docker \
        ci clean

# ---------- Configuration ----------

PYTHON ?= python3.12
VENV ?= .venv
VENV_BIN = $(VENV)/bin
PIP = $(VENV_BIN)/pip
DB_URL ?= postgresql+psycopg://selfrepair:selfrepair@localhost/selfrepair
COMPOSE = docker compose -f deploy/compose/docker-compose.dev.yml
FRONTEND_DIR = frontend

LOGS_DIR = logs
PIDS_DIR = .pids
API_PID = $(PIDS_DIR)/api.pid
WORKER_PID = $(PIDS_DIR)/worker.pid
FRONTEND_PID = $(PIDS_DIR)/frontend.pid
API_PORT ?= 8000
FRONTEND_PORT ?= 3000

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ============== Setup ==============

install: install-backend install-frontend ## Install backend (Python) + frontend (npm) deps
	@echo ""
	@echo "  Installed. Bring everything up with: \033[36mmake start\033[0m"

install-backend: venv ## Install backend Python deps in .venv (editable, [dev,server])
	$(PIP) install -e ".[dev,server]"

install-frontend: ## Install frontend npm deps
	cd $(FRONTEND_DIR) && npm install

install-clean: reset venv install ## Wipe .venv and reinstall everything from scratch

install-all: venv ## Install backend + frontend + huggingface/gitlab extras
	$(PIP) install -e ".[all]"
	cd $(FRONTEND_DIR) && npm install

dev: install ## Alias for install

venv: ## Create .venv (Python 3.11 or 3.12)
	@if [ ! -d "$(VENV)" ]; then \
	  echo "Creating $(VENV) with $(PYTHON)..."; \
	  $(PYTHON) -m venv $(VENV); \
	  $(PIP) install -U pip; \
	else \
	  echo "$(VENV) exists; use 'make reset' to recreate."; \
	fi

reset: stop ## Remove .venv (stops services first)
	rm -rf $(VENV)

# ============== Run lifecycle ==============

# `make start` is the one command devs run to bring up the whole stack.
# Order matters: backend first so the frontend dev server can proxy /api
# without hitting connection-refused errors during HMR boot.
start: stop ## Start backend (API + worker), then frontend
	@$(MAKE) --no-print-directory start-backend
	@$(MAKE) --no-print-directory _wait-backend
	@$(MAKE) --no-print-directory start-frontend
	@echo ""
	@echo "  \033[32mAPI\033[0m       http://localhost:$(API_PORT)/docs"
	@echo "  \033[32mFrontend\033[0m  http://localhost:$(FRONTEND_PORT)"
	@echo ""
	@echo "  make logs      tail logs from all three services"
	@echo "  make status    see what's running"
	@echo "  make stop      stop everything"

start-backend: ## Start API (uvicorn) + worker (arq) in the background
	@if [ ! -x "$(VENV_BIN)/uvicorn" ]; then \
	  echo "\033[31mBackend not installed.\033[0m Run: make install-backend"; \
	  exit 1; \
	fi
	@mkdir -p $(LOGS_DIR) $(PIDS_DIR)
	@echo "Starting API on :$(API_PORT)..."
	@nohup $(VENV_BIN)/uvicorn selfrepair.api.main:app \
	  --host 0.0.0.0 --port $(API_PORT) --reload \
	  > $(LOGS_DIR)/api.log 2>&1 & echo $$! > $(API_PID)
	@echo "Starting Arq worker..."
	@nohup $(VENV_BIN)/arq selfrepair.worker.main.WorkerSettings \
	  > $(LOGS_DIR)/worker.log 2>&1 & echo $$! > $(WORKER_PID)

start-frontend: ## Start the Vite dev server in the background
	@if [ ! -d "$(FRONTEND_DIR)/node_modules" ]; then \
	  echo "\033[31mFrontend not installed.\033[0m Run: make install-frontend"; \
	  exit 1; \
	fi
	@mkdir -p $(LOGS_DIR) $(PIDS_DIR)
	@echo "Starting frontend on :$(FRONTEND_PORT)..."
	@cd $(FRONTEND_DIR) && (nohup npm run dev \
	  > ../$(LOGS_DIR)/frontend.log 2>&1 & echo $$! > ../$(FRONTEND_PID))

start-deps: ## Bring up Postgres + Redis from docker compose (for local backend dev)
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm migrate

start-all: start-deps start ## Start postgres+redis (docker) + backend + frontend

_wait-backend:
	@printf "Waiting for API"
	@for i in $$(seq 1 30); do \
	  if curl -fsS http://localhost:$(API_PORT)/healthz >/dev/null 2>&1; then \
	    printf " \033[32mready\033[0m\n"; \
	    exit 0; \
	  fi; \
	  printf "."; \
	  sleep 1; \
	done; \
	printf " \033[33mtimed out\033[0m (check $(LOGS_DIR)/api.log)\n"

stop: stop-frontend stop-backend ## Stop everything (frontend, API, worker)

stop-backend: ## Stop API + worker
	@if [ -f $(API_PID) ]; then \
	  PID=$$(cat $(API_PID)); \
	  if kill -0 $$PID 2>/dev/null; then \
	    echo "Stopping API (pid $$PID)..."; \
	    kill $$PID 2>/dev/null || true; \
	    pkill -P $$PID 2>/dev/null || true; \
	  fi; \
	  rm -f $(API_PID); \
	fi
	@if [ -f $(WORKER_PID) ]; then \
	  PID=$$(cat $(WORKER_PID)); \
	  if kill -0 $$PID 2>/dev/null; then \
	    echo "Stopping worker (pid $$PID)..."; \
	    kill $$PID 2>/dev/null || true; \
	    pkill -P $$PID 2>/dev/null || true; \
	  fi; \
	  rm -f $(WORKER_PID); \
	fi
	@PIDS=$$(lsof -ti:$(API_PORT) 2>/dev/null || true); \
	if [ -n "$$PIDS" ]; then \
	  echo "Sweeping straggler on :$(API_PORT)..."; \
	  kill $$PIDS 2>/dev/null || true; \
	fi

stop-frontend: ## Stop the frontend dev server
	@if [ -f $(FRONTEND_PID) ]; then \
	  PID=$$(cat $(FRONTEND_PID)); \
	  if kill -0 $$PID 2>/dev/null; then \
	    echo "Stopping frontend (pid $$PID)..."; \
	    kill $$PID 2>/dev/null || true; \
	    pkill -P $$PID 2>/dev/null || true; \
	  fi; \
	  rm -f $(FRONTEND_PID); \
	fi
	@PIDS=$$(lsof -ti:$(FRONTEND_PORT) 2>/dev/null || true); \
	if [ -n "$$PIDS" ]; then \
	  echo "Sweeping straggler on :$(FRONTEND_PORT)..."; \
	  kill $$PIDS 2>/dev/null || true; \
	fi

stop-deps: ## Stop postgres + redis (docker compose)
	$(COMPOSE) down

stop-all: stop stop-deps ## Stop backend + frontend + deps

status: ## Show running service status
	@for svc in api worker frontend; do \
	  pidfile=$(PIDS_DIR)/$$svc.pid; \
	  if [ -f "$$pidfile" ] && kill -0 $$(cat "$$pidfile") 2>/dev/null; then \
	    printf "  %-9s \033[32mrunning\033[0m  pid %s\n" "$$svc" "$$(cat $$pidfile)"; \
	  else \
	    printf "  %-9s \033[2mstopped\033[0m\n" "$$svc"; \
	  fi; \
	done

logs: ## Tail logs from API + worker + frontend
	@mkdir -p $(LOGS_DIR)
	@touch $(LOGS_DIR)/api.log $(LOGS_DIR)/worker.log $(LOGS_DIR)/frontend.log
	@tail -F $(LOGS_DIR)/api.log $(LOGS_DIR)/worker.log $(LOGS_DIR)/frontend.log

logs-api: ## Tail API log only
	@mkdir -p $(LOGS_DIR) && touch $(LOGS_DIR)/api.log && tail -F $(LOGS_DIR)/api.log

logs-worker: ## Tail worker log only
	@mkdir -p $(LOGS_DIR) && touch $(LOGS_DIR)/worker.log && tail -F $(LOGS_DIR)/worker.log

logs-frontend: ## Tail frontend log only
	@mkdir -p $(LOGS_DIR) && touch $(LOGS_DIR)/frontend.log && tail -F $(LOGS_DIR)/frontend.log

# ============== Tests / lint ==============

test: ## Run unit tests
	$(VENV_BIN)/pytest tests/unit -q

test-all: ## Run all tests (unit + integration)
	$(VENV_BIN)/pytest tests -q

lint: ## Run ruff (no autofix) + mypy (non-blocking)
	$(VENV_BIN)/ruff check selfrepair tests
	$(VENV_BIN)/mypy selfrepair || true

format: ## Auto-fix ruff issues
	$(VENV_BIN)/ruff check --fix selfrepair tests
	$(VENV_BIN)/mypy selfrepair || true

typecheck: ## Strict mypy (blocking)
	$(VENV_BIN)/mypy selfrepair

# ============== Database ==============

migrate: ## Apply database migrations
	DATABASE_URL=$(DB_URL) $(VENV_BIN)/alembic upgrade head

migrate-down: ## Roll back the last migration
	DATABASE_URL=$(DB_URL) $(VENV_BIN)/alembic downgrade -1

migrate-rev: ## Generate a new migration (use M="message")
	DATABASE_URL=$(DB_URL) $(VENV_BIN)/alembic revision --autogenerate -m "$(M)"

# ============== Foreground run targets (no PID tracking) ==============

run-api: ## Run API in the foreground (Ctrl-C to stop)
	$(VENV_BIN)/uvicorn selfrepair.api.main:app --host 0.0.0.0 --port $(API_PORT) --reload

run-worker: ## Run worker in the foreground
	$(VENV_BIN)/arq selfrepair.worker.main.WorkerSettings

# ============== Docker (full stack) ==============

docker-build: ## Build the production backend image
	docker build -f deploy/docker/Dockerfile -t selfrepair:dev .

docker-up: ## Bring up the full dev stack (postgres+redis+api+worker)
	$(COMPOSE) up -d --build
	$(COMPOSE) run --rm migrate

docker-down: ## Tear down the full dev stack
	$(COMPOSE) down -v

docker-logs: ## Tail logs from the full dev stack
	$(COMPOSE) logs -f --tail=100

# ============== Frontend (foreground / image) ==============

frontend-install: install-frontend ## Alias for install-frontend

frontend-dev: ## Run Vite dev server in foreground
	cd $(FRONTEND_DIR) && npm run dev

frontend-build: ## Build static prod bundle into frontend/dist
	cd $(FRONTEND_DIR) && npm run build

frontend-lint: ## ESLint the frontend
	cd $(FRONTEND_DIR) && npm run lint

frontend-docker: ## Build the nginx-served console image
	docker build -t selfrepair-console:dev $(FRONTEND_DIR)

# ============== Meta ==============

ci: lint test ## What CI runs: lint + unit tests

verify: lint test frontend-lint frontend-build ## Full pre-push check: ruff + pytest + ESLint + vite build

clean: ## Remove build artefacts and caches (does not stop services or remove .venv)
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info htmlcov .coverage
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/node_modules/.vite
	rm -rf $(LOGS_DIR) $(PIDS_DIR)
