PY ?= .venv/bin/python
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
SEP := ;
else
SEP := :
endif
export PYTHONPATH := packages$(SEP)apps/api$(SEP)apps/worker
COMPOSE ?= docker compose

.PHONY: dev down install migrate seed-pricing seed-demo sync-prices test lint api web local-db purge-uploads

## Full stack (Postgres, Redis, API, worker, beat, web) with one command -> http://localhost:8080
dev:
	$(COMPOSE) up --build

down:
	$(COMPOSE) down

install:
	python -m venv .venv && $(PY) -m pip install -r requirements-dev.txt
	cd apps/web && npm install

## Database / catalog (uses PENDAR_DATABASE_URL; defaults to var/pendar-dev.db SQLite)
migrate:
	$(PY) -m pendar_api.cli migrate

seed-pricing: migrate
	$(PY) -m pendar_api.cli seed-pricing

seed-demo: seed-pricing
	$(PY) -m pendar_api.cli seed-demo-user

## Fetch official provider pages, normalize, guard, version (nightly in the worker)
sync-prices:
	$(PY) -m pendar_api.cli sync-prices

purge-uploads:
	$(PY) -m pendar_api.cli purge-uploads

test:
	$(PY) -m pytest -q
	cd apps/web && npm run typecheck

lint:
	$(PY) -m ruff check packages apps/api apps/worker tests

## Without Docker: API on :8000 and Vite on :5173 (run in two terminals)
api: seed-demo
	$(PY) -m uvicorn pendar_api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev
