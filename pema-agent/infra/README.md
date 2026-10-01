# infra

Everything needed to run Pema Agent: compose stack, Dockerfiles, environment template, database bootstrap and
migration scripts, backup/restore, and the Ubuntu-native guide (NVIDIA driver, Docker, Ollama, llama-server
roadmap, Tailscale/WireGuard, firewall, backups, UPS). Owner: package F (infrastructure part).

```
infra/
  docker-compose.yml        postgres+pgvector, redis, migrate, api  | profiles: worker, frontend, bridge, ollama, app
  .env.example              every variable, placeholders only (copy to .env, never commit it)
  docker/                   api.Dockerfile (api + worker + migrate), frontend.Dockerfile, bridge.Dockerfile
                            (+ <name>.Dockerfile.dockerignore, BuildKit picks them up)
  scripts/                  gen-secrets.sh  bootstrap-roles.sh  migrate.sh  backup-postgres.sh
                            restore-postgres.sh  pull-models.sh
  ubuntu/HUONG-DAN-UBUNTU.md  the operator guide (Vietnamese)
  ubuntu/systemd/           Ollama drop-in, llama-server units (roadmap), backup timer, docker-after-tailscale
```

## Quick start (from `pema-agent/`)

```
make infra-secrets      # infra/.env with random hex secrets; refuses to overwrite an existing file
make up                 # postgres, redis, migrate (one-shot), api   -> http://127.0.0.1:8000/healthz
make ps
make db-migrate         # re-run roles + alembic upgrade heads inside the compose network
make infra-config       # validate the compose file with every profile switched on
make down
```

Without `make` (Windows): the recipes are plain `docker compose -f infra/docker-compose.yml --env-file infra/.env ...`.

## Services and profiles

| Service | Profile | Notes | Depends on |
|---|---|---|---|
| `postgres` | default | `pgvector/pgvector:pg17`, scram, data checksums, port bound to `PEMA_PG_BIND` (default 127.0.0.1) | |
| `redis` | default | password (`PEMA_REDIS_PASSWORD`), AOF, `noeviction` (queue and locks must not be evicted) | |
| `migrate` | default | one-shot: `bootstrap-roles.sh` then `alembic upgrade heads`; safe to rerun | postgres |
| `api` | default | FastAPI via uvicorn `--factory pema.bootstrap:create_app`, healthcheck `/healthz` | migrate, redis |
| `worker` | `worker`, `app` | `python -m pema.workers.main`; same image as the API | **package G** creates `pema/workers/main.py`; until then the container exits at start |
| `frontend` | `frontend`, `app` | Next.js standalone server | **package E** (needs a `build` script and `output: "standalone"`) |
| `zalo-personal-bridge` | `bridge` | Node 22 + zca-js, internal only (never published), risk of Zalo account lock | **package C2** (needs `package.json`, `pnpm-lock.yaml`, `build`/`start` scripts) |
| `ollama`, `ollama-pull` | `ollama` | GPU container + model download; needs the NVIDIA Container Toolkit. The native install of the guide is the usual route | |

One image serves `api`, `worker` and `migrate` (`pema-agent-api:${PEMA_IMAGE_TAG}`): multi-stage, uv
`--locked` install, non-root user (uid 10001), no compiler. `uv sync --locked` fails the build when
`apps/api/pyproject.toml` has dependencies that `uv.lock` lacks (packages append libraries, package G regenerates
the lock); a local workaround is `--build-arg UV_SYNC_FLAGS=""`.

## Database roles and migrations

* Schemas, tables, RLS and grants are Alembic revisions `0001..0003` (package A). Infra never creates tables.
* `scripts/bootstrap-roles.sh` creates `be_app` and `agent_worker` (NOLOGIN, no superuser, no BYPASSRLS),
  sets their passwords from `PEMA_BE_APP_PASSWORD` / `PEMA_AGENT_WORKER_PASSWORD` (empty means the role stays
  NOLOGIN), creates the `vector` extension and, by default, revokes `CONNECT` from PUBLIC. Passwords are read by
  psql from the environment (`\getenv`), never from argv, and `log_statement` is switched off for the session so
  the `ALTER ROLE ... PASSWORD` text cannot reach the server log. Rerun it to rotate a password.
* `scripts/migrate.sh` waits for Postgres, runs the bootstrap, then `alembic upgrade heads` (all heads; package G
  merges them) and prints the head count and `alembic current`. `PEMA_SKIP_ROLE_BOOTSTRAP=true` skips the first step
  when a DBA manages roles.
* The owner role is the Postgres superuser in compose. For a managed database give `PEMA_MIGRATION_DATABASE_URL`
  an owner role that may `CREATE EXTENSION vector` (or let a superuser run `bootstrap-roles.sh` once).

## Network and secrets

* Every published port binds to a loopback address by default. To reach a service from another machine set the
  matching `PEMA_*_BIND` to that machine's Tailscale IP. Docker publishes ports around ufw, so the bind address,
  not the firewall, is the control that counts.
* `.env` is git-ignored; `gen-secrets.sh` creates it with mode 600. `PEMA_SECRET_ENCRYPTION_KEY` has no recovery:
  keep an offline copy.
* Inside the compose network the services get their URLs composed from the passwords (host names `postgres`,
  `redis`); the `localhost` URLs in `.env` are for tools run on the host.

## Backups

`scripts/backup-postgres.sh` (verified dump + globals, encrypted with age or gpg, retention, off-site hook) and
`scripts/restore-postgres.sh --verify|--restore` (never overwrites the live database). Plaintext is refused unless
`PEMA_BACKUP_ALLOW_PLAINTEXT=true`. Nightly timer: `ubuntu/systemd/pema-backup.{service,timer}`. Details in the guide.
