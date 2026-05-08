# =============================================================================
#  Evolver — Makefile per task ricorrenti
# =============================================================================
#  Uso:
#      make help           # mostra questa lista
#      make up             # docker compose up -d
#      make down           # docker compose down
#      make migrate        # alembic upgrade head dentro container backend
#      make shell-be       # shell nel container backend
#      make backfill       # backfill dati storici BTC + ETH
#      make test           # pytest backend
#      make lint           # ruff + mypy
#      make fmt            # ruff format
#      make logs           # tail logs
# =============================================================================

.PHONY: help up down restart migrate shell-be shell-db backfill test lint fmt logs reset

DC := docker compose

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

up: ## Avvia tutti i servizi (postgres, redis, backend)
	$(DC) up -d

down: ## Ferma tutti i servizi
	$(DC) down

restart: ## Riavvia tutto (down + up)
	$(DC) down && $(DC) up -d

migrate: ## Applica migration Alembic
	$(DC) exec backend alembic upgrade head

migrate-revision: ## Crea nuova migration: make migrate-revision MSG="add_xxx"
	$(DC) exec backend alembic revision --autogenerate -m "$(MSG)"

shell-be: ## Shell Python nel container backend
	$(DC) exec backend python

shell-db: ## psql nel container postgres
	$(DC) exec postgres psql -U evolver -d evolver

backfill: ## Backfill storico BTC + ETH (5 anni, ~30 min)
	$(DC) exec backend python -m scripts.backfill --symbols BTC/USDT,ETH/USDT --years 5

test: ## Esegui pytest
	cd backend && uv run pytest

lint: ## Lint + type check
	cd backend && uv run ruff check . && uv run mypy app

fmt: ## Format codice
	cd backend && uv run ruff format . && uv run ruff check --fix .

logs: ## Tail logs di tutti i servizi
	$(DC) logs -f

logs-be: ## Tail logs solo backend
	$(DC) logs -f backend

reset: ## DANGER: cancella DB e ricrea tutto
	$(DC) down -v
	$(DC) up -d postgres redis
	@sleep 5
	$(DC) up -d backend
	@sleep 3
	$(DC) exec backend alembic upgrade head
