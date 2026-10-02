# infra

Everything needed to run Pema Agent: compose stack, Dockerfiles, environment template, database bootstrap and
migration scripts, backup/restore, and the Ubuntu-native guide (NVIDIA driver, Docker, Ollama, llama-server
roadmap, Tailscale/WireGuard, firewall, backups, UPS). Owner: package F (infrastructure part).

Branch `feat/single-tenant`: **one system = one clinic** (section below).

```
infra/
  docker-compose.yml        postgres+pgvector, redis, migrate, api  | profiles: worker, frontend, proxy, bridge, app (ollama paused)
  docker-compose.proxy.yml  override for "behind the proxy": api and frontend stop publishing ports (see Reverse proxy)
  caddy/                    Caddyfile (one host) + modes/{auto,internal,off}.caddy (TLS mode, chosen by PEMA_PROXY_TLS)
  .env.example              every variable, placeholders only (copy to .env, never commit it)
  docker/                   api.Dockerfile (api + worker + migrate), frontend.Dockerfile, bridge.Dockerfile
                            (+ <name>.Dockerfile.dockerignore, BuildKit picks them up)
  scripts/                  gen-secrets.sh  bootstrap-roles.sh  migrate.sh  backup-postgres.sh
                            restore-postgres.sh  pull-models.sh
  ubuntu/HUONG-DAN-UBUNTU.md  the operator guide (Vietnamese)
  ubuntu/systemd/           Ollama drop-in, llama-server units (roadmap), backup timer, docker-after-tailscale
```

## One system, one clinic

An installation serves exactly ONE clinic, with its own server, Postgres, Redis, Zalo accounts and encryption keys.
The reason is the security bar of clinics, hospitals and banks: patient data of two organisations never shares a
database, a Redis, a key or a process, so there is nothing for a bug to leak across. Nothing in this stack selects a
clinic: no clinic slug at login, no clinic segment in the webhook paths, no `--clinic` option, no row level security.

* `PEMA_CLINIC_NAME` (default `Pema Clinic`) and the optional `PEMA_CLINIC_ID` (UUID) in `infra/.env` are read by the
  migration (`st_0009_single_tenant`), which creates the one row of `clinic.clinic` on an empty database. Afterwards
  the installed clinic is never renamed and never gets another id; the variables only matter on the first run (and
  `PEMA_CLINIC_ID`, when set, must match the database or `migrate.sh` stops).
* The database enforces it: `clinic.clinic` cannot hold a second row and the row cannot be deleted. `migrate.sh` checks
  the count after the upgrade and prints the clinic, for example
  `migrate: clinic 'Pema Clinic' (id ...), exactly one row in clinic.clinic`.
* One clinic can still have several Zalo accounts (bot or personal); they are set up in the dashboard.
* Compose passes the two variables to `migrate`, `api` and `worker` (anchor `x-backend-env`).

**A second clinic is a second, completely separate stack.** Never a second row in the same database. Preferably on
another machine; on the same Docker host only with everything below different:

| What | Why it must differ |
|---|---|
| a new copy of `infra/.env` (`make infra-secrets` writes fresh random values) | no secret is shared |
| `PEMA_JWT_SECRET`, `PEMA_SECRET_ENCRYPTION_KEY`, the DB/Redis/bridge passwords | tokens, stored Zalo credentials and API keys of clinic A must not open with clinic B's key |
| `COMPOSE_PROJECT_NAME=pema-clinic-b` in that `.env` (or `docker compose -p`) | own containers, networks and volumes (`pg-data`, `redis-data`, `pema-data`, `caddy-data`) |
| its own Postgres and Redis (the same project name gives them) | Postgres roles `be_app`/`agent_worker` are cluster-wide: never point two stacks at one cluster |
| host ports `PEMA_PG_PORT`, `PEMA_REDIS_PORT`, `PEMA_API_PORT`, `PEMA_FRONTEND_PORT`, `PEMA_PROXY_*_PORT` (or other bind IPs) | two stacks cannot publish the same port on one host |
| `PEMA_PROXY_SUBNET`, `PEMA_PROXY_IP_RANGE`, `PEMA_PROXY_IP` | the `edge` network has a fixed subnet |
| its own domain (`PEMA_PUBLIC_DOMAIN`) and certificate | one clinic, one address |
| its own Zalo accounts and webhook base URL | the account belongs to one clinic |
| its own `PEMA_CLINIC_NAME` (and `PEMA_CLINIC_ID` if you fix it) | |
| its own `PEMA_BACKUP_DIR` and age key | a dump is the whole clinic |

## Quick start (from `pema-agent/`)

```
make infra-secrets      # infra/.env with random hex secrets; refuses to overwrite an existing file
make up                 # postgres, redis, migrate (one-shot), api   -> http://127.0.0.1:8000/healthz
make ps
make db-migrate         # re-run roles + alembic upgrade heads inside the compose network; prints the one clinic
make infra-config       # validate the compose file with every profile switched on
make down
make up-proxy            # the stack behind Caddy (profile proxy + worker + docker-compose.proxy.yml); make down-proxy stops it
make retention-dry-run  # what the data-retention job WOULD delete (api container: clinic scope, worker container: agent scope)
```

Without `make` (Windows): the recipes are plain `docker compose -f infra/docker-compose.yml --env-file infra/.env ...`.

## Services and profiles

| Service | Profile | Notes | Depends on |
|---|---|---|---|
| `postgres` | default | `pgvector/pgvector:pg17`, scram, data checksums, port bound to `PEMA_PG_BIND` (default 127.0.0.1) | |
| `redis` | default | password (`PEMA_REDIS_PASSWORD`), AOF, `noeviction` (queue and locks must not be evicted) | |
| `migrate` | default | one-shot: `bootstrap-roles.sh`, `alembic upgrade heads` (creates the clinic on an empty database), then checks that `clinic.clinic` holds exactly one row and prints its name; safe to rerun | postgres |
| `api` | default | FastAPI via uvicorn `--factory pema.bootstrap:create_app`, healthcheck `/healthz` | migrate, redis |
| `worker` | `worker`, `app` | `python -m pema.workers.main`; same image as the API | |
| `frontend` | `frontend`, `app`, `proxy` | Next.js standalone server; route handlers forward `/api/v1` and `/healthz` to `PEMA_API_INTERNAL_URL`, an ordinary runtime variable read on every request (no build argument, no rebuild to change it), healthcheck `/login` | api |
| `caddy` | `proxy` | Reverse proxy, the only service that publishes 80/443, attached only to the `edge` network (api and frontend); see "Reverse proxy" | api, frontend |
| `zalo-personal-bridge` | `bridge` | Node 22 + zca-js run by tsx (no build step; tsx is a runtime dependency), internal only (`expose`, never published; listens on 0.0.0.0 inside the container so the API can reach it), healthcheck `/health`, risk of Zalo account lock. Disabled unless `PEMA_ZALO_PERSONAL_ENABLED=true` | |
| `ollama`, `ollama-pull` | `ollama` | **TẠM TẮT LLM LOCAL (2026-10-02)**: commented out in `docker-compose.yml`; the agent uses a third-party LLM API (`LLM_*` in `.env`). When re-enabled: GPU container + model download; needs the NVIDIA Container Toolkit | |

One image serves `api`, `worker` and `migrate` (`pema-agent-api:${PEMA_IMAGE_TAG}`): multi-stage, uv
`--locked` install, non-root user (uid 10001), no compiler. `uv sync --locked` fails the build when
`apps/api/pyproject.toml` has dependencies that `uv.lock` lacks (packages append libraries, regenerate the lock
with `uv lock`); a local workaround is `--build-arg UV_SYNC_FLAGS=""`.

## Reverse proxy (profile `proxy`)

Two ways to run, and they do not mix:

* **Development, no proxy** (`make up`, `--profile app`): api, frontend, postgres and redis publish on loopback
  (`PEMA_*_BIND`), the browser opens `http://127.0.0.1:3000`. No TLS. The API sees the frontend container as the client
  of every login, so the login rate limit is shared by all users of that dashboard; fine for one developer.
* **Behind Caddy** (a clinic server, or any machine other people reach): Caddy publishes 80 and 443 and nothing else does.

```
docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file infra/.env     --profile proxy --profile worker up -d --build
```

`docker-compose.proxy.yml` empties the `ports` of `api` and `frontend` (`!reset`, Compose 2.24+) and leaves them
`expose`d on the compose networks. Postgres and Redis keep their loopback ports for host tools; block them in the host
firewall if the machine has a public address. `--profile proxy` also starts the dashboard (the proxy is useless without
it); add `--profile worker` for the agent worker.

**TLS mode** (`PEMA_PROXY_TLS` in `.env`, with the address in `PEMA_PUBLIC_DOMAIN`):

| Mode | When | `PEMA_PUBLIC_DOMAIN` | Notes |
|---|---|---|---|
| `auto` (default) | a real domain points at this machine | `clinic.example.com` | Let's Encrypt, renewed by Caddy; needs 80 and 443 reachable from the internet and `PEMA_PROXY_BIND=0.0.0.0` (or the public IP); HSTS (1 year, no subdomains) is sent |
| `internal` | no domain yet | `localhost`, `pema.lan`, a MagicDNS name | Caddy's own CA signs the certificate; browsers warn until the CA root is installed (below); no HSTS |
| `off` | plain HTTP **only** over Tailscale/WireGuard | `http://100.x.y.z` | also `PEMA_PROXY_BIND=<tailscale ip>` and `PEMA_SESSION_COOKIE_SECURE=false` (a Secure cookie is not sent over http, so login would loop); never on the public internet |

Routing: `/api/v1/*` and `/healthz` go to `api:8000`, everything else to `frontend:3000`. The Zalo bridge webhook
(`/api/v1/webhooks/zalo-bridge/<account_id>`, matched as `/api/v1/webhooks/zalo-bridge/*`) is answered 404 from outside: the bridge talks to the API over the compose network.
`/docs`, `/openapi.json` and every other path never reach the API. Postgres, Redis and the bridge cannot be routed:
Caddy is attached only to the `edge` network (fixed subnet `PEMA_PROXY_SUBNET`, default `172.29.80.0/24`; Caddy is
`PEMA_PROXY_IP`, default `.2`), where only `api` and `frontend` live. Change the subnet and the IP together if the
subnet collides with one of yours (a running stack needs `down` first, networks cannot change subnet in place).

What Caddy does to every answer (the one exception: the automatic 308 redirect from http to https is built by Caddy
itself and still carries `Server: Caddy`): removes `Server`, `Via` and `X-Powered-By`, adds `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Content-Security-Policy: frame-ancestors 'none'`, `Referrer-Policy`, `Permissions-Policy` (and HSTS in mode `auto`);
cuts a request body larger than 4 MiB with 413 before the API reads it (the API's own `MAX_BODY_BYTES`; only the two
knowledge-base upload routes get 105 MiB, above `KB_MAX_FILE_MB` at most 100); `read_header` 10 s against slowloris;
compresses with zstd and gzip. The access log (stdout, JSON) leaves out the query string, `Cookie`, `Authorization`,
`Set-Cookie` and the query of `Referer`; it still holds the client IP and the path (personal data of the visitor,
retention is your decision).

**Client address and cookie.** Caddy overwrites `X-Forwarded-For` with the address it sees (it trusts no one in front of
it). The API believes `X-Forwarded-For` only when the TCP peer is in `PEMA_TRUSTED_PROXIES` (default: Caddy's fixed
address), takes the first entry from the right that is not itself a trusted proxy, and uses the socket address for
everyone else (`pema/api/client_ip.py`); `PEMA_DASHBOARD_BEHIND_PROXY=true` is the switch and an empty list trusts
nobody. If another proxy or a CDN is in front of Caddy, add its range to `PEMA_TRUSTED_PROXIES` **and** configure
Caddy's `servers { trusted_proxies ... }` for it; otherwise leave both alone. The session cookie is `HttpOnly`,
`SameSite=Lax` and `Secure` (`PEMA_SESSION_COOKIE_SECURE=true`).

**Mode `internal`: install the CA.** `docker compose exec caddy cat /data/caddy/pki/authorities/local/root.crt > pema-root.crt`,
then import it as a trusted root on each device (the file is the public certificate, not a secret; the private key
stays in the `caddy-data` volume). Volumes `caddy-data` (certificates, CA, ACME account) and `caddy-config` persist
across restarts; back up `caddy-data` or accept a new certificate request after a loss.

**Webhook.** In mode `auto`, set `PEMA_ZALO_BOT_WEBHOOK_BASE_URL=https://<PEMA_PUBLIC_DOMAIN>` (no trailing slash) if the
Zalo Bot runs in `webhook` mode; the Bot webhook route is `/api/v1/webhooks/zalo-bot/<account_id>` (no clinic segment
since `feat/single-tenant`; the path is owned by the Zalo channel package) and passes through. If a webhook was registered
at Zalo with the old path (`.../zalo-bot/<clinic>/<account_id>`), re-register it (restart the account) after the upgrade.

**Changing the API address of the dashboard** (it is a runtime variable): set `PEMA_API_INTERNAL_URL` in `.env`, then
`docker compose ... up -d frontend`. No rebuild. Without a proxy it is the only place the dashboard learns where the API is.

## Database roles and migrations

* Schemas, tables and grants are Alembic revisions (package A, then each package; `st_0009_single_tenant` is the head).
  Infra never creates tables. There is **no row level security** any more: the database holds one clinic, so the
  isolation surface is the infrastructure (this stack, its own database and Redis) plus the role grants below. `be_app`
  reads and writes every row of the tables it holds a grant on; `agent_worker` has no privilege on `clinic.*` and
  reaches the clinic only through the `clinic_agent` views and functions.
* `scripts/bootstrap-roles.sh` creates `be_app` and `agent_worker` (NOLOGIN, no superuser, no BYPASSRLS),
  sets their passwords from `PEMA_BE_APP_PASSWORD` / `PEMA_AGENT_WORKER_PASSWORD` (empty means the role stays
  NOLOGIN), creates the `vector` extension and, by default, revokes `CONNECT` from PUBLIC. Passwords are read by
  psql from the environment (`\getenv`), never from argv, and `log_statement` is switched off for the session so
  the `ALTER ROLE ... PASSWORD` text cannot reach the server log. Rerun it to rotate a password.
* `scripts/migrate.sh` waits for Postgres, runs the bootstrap, then `alembic upgrade heads` (one head since
  `h_0008_merge_heads`; `st_0009_single_tenant` on top), prints the head count and `alembic current`, and finally checks
  that `clinic.clinic` holds exactly one row (fails otherwise, also when `PEMA_CLINIC_ID` differs from the database) and
  prints the clinic name and id. `PEMA_SKIP_ROLE_BOOTSTRAP=true` skips the first step when a DBA manages roles.
* Upgrading a database that came from `feat/ai-agent-backend` (multi-tenant): `st_0009` refuses to run when it holds two
  or more clinics (split or merge it first); with exactly one clinic it keeps that row, its id and its name.
* The owner role is the Postgres superuser in compose. For a managed database give `PEMA_MIGRATION_DATABASE_URL`
  an owner role that may `CREATE EXTENSION vector` (or let a superuser run `bootstrap-roles.sh` once).

## Network and secrets

* Every published port binds to a loopback address by default (Caddy included: a public site sets `PEMA_PROXY_BIND`). To reach a service from another machine set the
  matching `PEMA_*_BIND` to that machine's Tailscale IP. Docker publishes ports around ufw, so the bind address,
  not the firewall, is the control that counts.
* `.env` is git-ignored; `gen-secrets.sh` creates it with mode 600. `PEMA_SECRET_ENCRYPTION_KEY` has no recovery:
  keep an offline copy.
* Inside the compose network the services get their URLs composed from the passwords (host names `postgres`,
  `redis`); the `localhost` URLs in `.env` are for tools run on the host.

## Backups

`scripts/backup-postgres.sh` (verified dump + globals, encrypted with age or gpg, retention, off-site hook) and
`scripts/restore-postgres.sh --verify|--restore` (never overwrites the live database; it also checks that the restored
database holds exactly one clinic and prints its name). With one clinic per database a dump is the whole clinic: every
patient, message and stored credential. Because there is no row level security to fall back on, who may read the backup
directory and the age private key is as important as who holds the `be_app` password. Plaintext is refused unless
`PEMA_BACKUP_ALLOW_PLAINTEXT=true`. Nightly timer: `ubuntu/systemd/pema-backup.{service,timer}`. Details in the guide.
