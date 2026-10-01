# Pema Agent: common commands. Run from pema-agent/. Needs uv, pnpm, and docker for the db targets.
# Windows without make: run the commands of each recipe by hand (they are plain uv/pnpm/docker calls).

BACKEND := backend
FRONTEND := frontend
COMPOSE := docker compose -f infra/docker-compose.yml --env-file infra/.env
OPENAPI := $(BACKEND)/apps/api/openapi.json
# Load infra/.env (if present) into the environment of one recipe line.
LOAD_ENV := set -a; if [ -f ../infra/.env ]; then . ../infra/.env; fi; set +a;

.PHONY: help setup lint format typecheck test test-db openapi types db-upgrade db-downgrade up down clean

help:
	@echo "setup       install Python (uv) and frontend (pnpm) dependencies"
	@echo "lint        ruff + pyright (strict) + import-linter"
	@echo "format      ruff format + autofix"
	@echo "typecheck   pyright (backend) and tsc (frontend)"
	@echo "test        pytest (DB tests skip unless PEMA_TEST_DATABASE_URL is set)"
	@echo "test-db     pytest against PEMA_TEST_DATABASE_URL (a THROWAWAY Postgres with pgvector)"
	@echo "openapi     regenerate $(OPENAPI)"
	@echo "types       regenerate frontend TypeScript types from the OpenAPI file"
	@echo "db-upgrade  alembic upgrade heads for ctx, clinic, clinic_agent, agent (reads infra/.env)"
	@echo "up / down   start / stop the dev stack (postgres+pgvector, redis) via infra/docker-compose.yml"

setup:
	cd $(BACKEND) && uv sync --all-packages
	cd $(FRONTEND) && pnpm install

lint:
	cd $(BACKEND) && uv run ruff check .
	cd $(BACKEND) && uv run ruff format --check .
	cd $(BACKEND) && uv run pyright
	cd $(BACKEND) && uv run lint-imports

format:
	cd $(BACKEND) && uv run ruff check --fix .
	cd $(BACKEND) && uv run ruff format .

typecheck:
	cd $(BACKEND) && uv run pyright
	cd $(FRONTEND) && pnpm run check:types

test:
	cd $(BACKEND) && uv run pytest

test-db:
	@test -n "$$PEMA_TEST_DATABASE_URL" || (echo "set PEMA_TEST_DATABASE_URL to a throwaway Postgres (see backend/apps/api/tests/test_database.py)"; exit 1)
	cd $(BACKEND) && uv run pytest apps/api/tests/test_database.py -v

openapi:
	cd $(BACKEND) && uv run python -m pema.api.export_openapi

types: openapi
	cd $(FRONTEND) && pnpm run gen:types && pnpm run check:types

db-upgrade:
	cd $(BACKEND) && $(LOAD_ENV) uv run alembic -c apps/api/alembic.ini upgrade heads

db-downgrade:
	cd $(BACKEND) && $(LOAD_ENV) uv run alembic -c apps/api/alembic.ini downgrade base

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

clean:
	rm -rf $(BACKEND)/.venv $(FRONTEND)/node_modules
