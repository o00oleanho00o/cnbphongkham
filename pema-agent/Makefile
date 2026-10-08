# Pema Agent: common commands. Run from pema-agent/. Needs uv, pnpm, and docker for the db targets.
# Windows without make: run the commands of each recipe by hand (they are plain uv/pnpm/docker calls).
# One checkout + one infra/.env = ONE clinic (single tenant): no target takes a clinic slug or id. A second clinic is
# a second stack with its own infra/.env (infra/README.md "One system, one clinic").

BACKEND := backend
FRONTEND := frontend
COMPOSE := docker compose -f infra/docker-compose.yml --env-file infra/.env
# Behind the Caddy reverse proxy: the override stops api and frontend from publishing ports (infra/README.md).
COMPOSE_PROXY := docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file infra/.env
OPENAPI := $(BACKEND)/apps/api/openapi.json
# Load infra/.env (if present) into the environment of one recipe line.
LOAD_ENV_ROOT := set -a; if [ -f infra/.env ]; then . infra/.env; fi; set +a;
LOAD_ENV := set -a; if [ -f ../infra/.env ]; then . ../infra/.env; fi; set +a;

.PHONY: help setup lint format typecheck test test-db openapi types db-upgrade db-downgrade clean \
        infra-secrets infra-config up up-app up-proxy down down-proxy logs ps db-migrate db-bootstrap \
        retention-dry-run backup restore-verify

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
	@echo "infra-secrets  create infra/.env with random secrets (refuses to overwrite)"
	@echo "infra-config   docker compose config (every profile, also proxy with the override; uses infra/.env or a throwaway one)"
	@echo "up / down      start / stop postgres, redis, migrate, api (profile: frontend)"
	@echo "up-app         up + frontend"
	@echo "up-proxy       stack behind Caddy (profile proxy + docker-compose.proxy.yml); down-proxy stops it"
	@echo "retention-dry-run  python -m pema.retention.cli --dry-run in the api container (counts, deletes nothing)"
	@echo "db-migrate     roles + alembic upgrade heads inside the compose network (one-shot migrate service); checks and prints the one clinic"
	@echo "db-bootstrap   only the role/password bootstrap, from the host (needs psql); rotates passwords"
	@echo "backup / restore-verify   infra/scripts/backup-postgres.sh, restore into a scratch DB (FILE=...)"

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

infra-secrets:
	infra/scripts/gen-secrets.sh

# .env.example leaves the secrets empty on purpose (compose refuses to start without them), so without an
# infra/.env the check runs against a throwaway env file with random values.
infra-config:
	@f=infra/.env; \
	if [ ! -f "$$f" ]; then d=$$(mktemp -d); f="$$d/env"; infra/scripts/gen-secrets.sh "$$f" >/dev/null; fi; \
	docker compose -f infra/docker-compose.yml --env-file "$$f" --profile app config --quiet && \
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file "$$f" --profile proxy config --quiet && \
	echo "compose file valid (default+app, and proxy with the override)"

up:
	$(COMPOSE) up -d --build

up-app:
	$(COMPOSE) --profile app up -d --build

# TẠM TẮT LLM LOCAL (2026-10-02): re-enable together with the `ollama` services in infra/docker-compose.yml
# (and add up-ollama back to .PHONY).
# up-ollama:
# 	$(COMPOSE) --profile ollama up -d

# The stack behind Caddy (infra/README.md "Reverse proxy"). Needs infra/.env with PEMA_PROXY_TLS and PEMA_PUBLIC_DOMAIN.
up-proxy:
	$(COMPOSE_PROXY) --profile proxy up -d --build

down:
	$(COMPOSE) down

down-proxy:
	$(COMPOSE_PROXY) --profile proxy down

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

db-migrate:
	$(COMPOSE) run --rm migrate

# Counts what the retention job WOULD delete, deletes nothing. The API container runs the `clinic` scope.
retention-dry-run:
	$(COMPOSE) exec api python -m pema.retention.cli --dry-run

db-bootstrap:
	$(LOAD_ENV_ROOT) infra/scripts/bootstrap-roles.sh

backup:
	$(LOAD_ENV_ROOT) infra/scripts/backup-postgres.sh

restore-verify:
	@test -n "$(FILE)" || (echo "usage: make restore-verify FILE=/var/backups/pema/pema-YYYYmmdd-HHMMSS.tar.age"; exit 1)
	infra/scripts/restore-postgres.sh --verify "$(FILE)"

clean:
	rm -rf $(BACKEND)/.venv $(FRONTEND)/node_modules
