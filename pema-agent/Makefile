# Agent: common commands. Run from pema-agent/. Needs uv, bun, and docker for the stack targets.
# Windows without make: run the commands of each recipe by hand (they are plain uv/bun/docker calls).

BACKEND := backend
FRONTEND := frontend
COMPOSE := docker compose -f infra/docker-compose.yml --env-file infra/.env
# Behind the Caddy reverse proxy: the override stops the frontend from publishing its port (infra/README.md).
COMPOSE_PROXY := docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file infra/.env
# Load infra/.env (if present) into the environment of one recipe line.
LOAD_ENV_ROOT := set -a; if [ -f infra/.env ]; then . infra/.env; fi; set +a;

.PHONY: help setup lint format typecheck clean infra-secrets infra-config up up-proxy down down-proxy logs ps \
        db-migrate backup restore-verify

help:
	@echo "setup       install Python (uv) and frontend (bun) dependencies"
	@echo "lint        ruff + pyright (strict) + import-linter"
	@echo "format      ruff format + autofix"
	@echo "typecheck   pyright (backend) and tsc (frontend)"
	@echo "infra-secrets  create infra/.env with random secrets (refuses to overwrite)"
	@echo "infra-config   docker compose config (default, and proxy with the override; uses infra/.env or a throwaway one)"
	@echo "up / down      start / stop postgres, agent-migrate, agent, egress, zalo, frontend"
	@echo "up-proxy       stack behind Caddy (profile proxy + docker-compose.proxy.yml); down-proxy stops it"
	@echo "db-migrate     the agent's role and migrations (one-shot agent-migrate service)"
	@echo "backup / restore-verify   infra/scripts/backup-postgres.sh, restore into a scratch DB (FILE=...)"

setup:
	cd $(BACKEND) && uv sync --all-packages
	cd $(FRONTEND) && bun install

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
	cd $(FRONTEND) && bun run check:types

infra-secrets:
	infra/scripts/gen-secrets.sh

# .env.example leaves the secrets as placeholders, so without an infra/.env the check runs against a throwaway env
# file with random values.
infra-config:
	@f=infra/.env; \
	if [ ! -f "$$f" ]; then d=$$(mktemp -d); f="$$d/env"; infra/scripts/gen-secrets.sh "$$f" >/dev/null; fi; \
	docker compose -f infra/docker-compose.yml --env-file "$$f" config --quiet && \
	docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file "$$f" --profile proxy config --quiet && \
	echo "compose file valid (default, and proxy with the override)"

up:
	$(COMPOSE) up -d --build

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
	$(COMPOSE) run --rm agent-migrate

backup:
	$(LOAD_ENV_ROOT) infra/scripts/backup-postgres.sh

restore-verify:
	@test -n "$(FILE)" || (echo "usage: make restore-verify FILE=/var/backups/rag-agent/backup-YYYYmmdd-HHMMSS.tar.age"; exit 1)
	infra/scripts/restore-postgres.sh --verify "$(FILE)"

clean:
	rm -rf $(BACKEND)/.venv $(FRONTEND)/node_modules
