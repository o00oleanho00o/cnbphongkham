# infra

The Contete Agent stack on one machine: Postgres (database `contete_agent`), the agent, its way out to the internet
(`egress`), the Zalo connector and the dashboard. Compose files, Caddy, backup and restore scripts live here.

## Quick start (from the repo root)

```
make infra-secrets      # infra/.env with random hex secrets; refuses to overwrite an existing file
make up                 # postgres, agent-migrate (one-shot), agent, egress, zalo, frontend -> http://127.0.0.1:3000
make ps
make db-migrate         # the agent's role and migrations again (safe to rerun)
make infra-config       # validate the compose files (default, and proxy with the override)
make down
make up-proxy           # the stack behind Caddy (profile proxy + docker-compose.proxy.yml); make down-proxy stops it
```

Without `make` (Windows): the recipes are plain `docker compose -f infra/docker-compose.yml --env-file infra/.env ...`.
One command with demo values, from the repo root: `docker compose up --build` (the root `docker-compose.yml`).

The first sign-in on the dashboard creates the agent's admin account (plugin `web`). The model's API key is set on the
dashboard and stored encrypted in the database; it is never in `.env`.

## Services and profiles

| Service | Profile | Notes |
|---|---|---|
| `postgres` | default | `pgvector/pgvector:pg17`, scram, data checksums, port bound to `CONTETE_PG_BIND` (default 127.0.0.1); the only database is `contete_agent` |
| `agent-migrate` | default | one-shot: `agent db bootstrap-role` (role `agent_rt_app`, CONNECT for it alone), the agent's Alembic, then `agent db migrate-plugins` |
| `agent` | default | `agent serve --profile agents/rag`; internal only (`expose` 8088); read-only container, `cap_drop ALL`, writes only `/data` (volume `agent-home`, holds its secret key) and `/tmp` |
| `egress` | default | Squid (`infra/egress/squid.conf`): the model, embedding and TypeSafe clients of the agent and everything the `zalo` connector sends to Zalo go out through it. Phase 1 logs every destination and blocks none |
| `zalo` | default | The Zalo connector (`connectors/zalo/`, its own image): Zalo Bot and personal accounts, its own pages. Talks to the agent only through the signed connector protocol (`docs/CONNECTOR-PROTOCOL.md`) |
| `frontend` | default | The dashboard: TanStack Start server run by bun. Signs staff in with the agent's account, keeps the login in an httpOnly cookie, forwards `/agent/...` to `CONTETE_AGENT_INTERNAL_URL` and `/connectors/<name>/...` to `CONTETE_CONNECTOR_URLS` |
| `caddy` | `proxy` | Reverse proxy, the only service that publishes 80/443; see "Reverse proxy" |
| `ollama`, `ollama-pull` | `ollama` | Commented out in `docker-compose.yml` (2026-10-02); the agent uses a model API |

## Reverse proxy (profile `proxy`)

* **No proxy** (`make up`): the dashboard publishes on loopback (`CONTETE_FRONTEND_BIND`, `CONTETE_FRONTEND_PORT`), the
  browser opens `http://127.0.0.1:3000`. No TLS.
* **Behind Caddy** (any machine other people reach): `make up-proxy`, which is

```
docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file infra/.env --profile proxy up -d --build
```

`docker-compose.proxy.yml` turns the loopback port of the frontend into `expose`, so Caddy is the only container that
publishes 80 and 443. Pick one TLS mode in `infra/.env`:

| `CONTETE_PROXY_TLS` | When | `CONTETE_PUBLIC_DOMAIN` | Notes |
|---|---|---|---|
| `auto` (default) | a real domain points at this machine | `agent.example.com` | Let's Encrypt, renewed by Caddy; needs 80 and 443 reachable from the internet and `CONTETE_PROXY_BIND=0.0.0.0` (or the public IP) |
| `internal` | no domain yet | `localhost` or `contete.lan` | Caddy signs its own certificate; install its CA root on the devices |
| `off` | only over Tailscale or WireGuard | `http://100.64.0.10` | plain HTTP; also set `CONTETE_SESSION_COOKIE_SECURE=false` and `CONTETE_PROXY_BIND` to the Tailscale IP |

Routing (`infra/caddy/Caddyfile`): everything goes to `frontend:3000`. Its server answers the sign-in, forwards
`/agent/...` to the agent and `/connectors/<name>/...` to the connectors. Postgres, the agent and the connectors are not
routed and cannot be: Caddy is attached only to the `edge` network, where only the frontend lives. A request body larger
than 13 MiB is cut with 413; request headers must arrive in 10 s. The access log leaves out query strings, cookies and
`Authorization`.

Webhook mode of Zalo Bot (`ZALO_PUBLIC_URL`) needs a route to the connector's `/v1/hooks/zalo/bot/<account>`, which
this Caddyfile does not have; leave it empty for long polling.

## Database, roles and migrations

* One database, `contete_agent` (schema `agent_rt`), and one runtime role, `agent_rt_app`, with CONNECT on that
  database alone; no `dblink`, no `postgres_fdw` (.claude/rules/agent-boundary.md, L1).
* Tables are migrations; infra never creates tables. The agent has one Alembic baseline (`backend/apps/agent/alembic`)
  and each plugin that keeps tables ships its own SQL files (`agent db migrate-plugins`).
* The owner role is the Postgres superuser in compose. For a managed database give the owner URL a role that may
  create the database `contete_agent` and `CREATE EXTENSION vector` in it.

## Network and secrets

* Every published port binds to a loopback address by default (Caddy included: a public site sets
  `CONTETE_PROXY_BIND`). To reach a service from another machine set the matching `CONTETE_*_BIND` to that machine's
  Tailscale IP. Docker publishes ports around ufw, so the bind address, not the firewall, is the control that counts.
* `.env` is git-ignored; `gen-secrets.sh` creates it with mode 600: keep an offline copy. The agent's secret key
  (it seals the model keys) is in the `agent-home` volume and has no recovery: the backup takes it with the database.
  The Zalo seal key `CONTETE_ZALO_SECRET_KEY` is in `.env`, the sealed tokens in the `zalo-data` volume.

## Zalo connector

1. `CONTETE_ZALO_SECRET_KEY` must be set in `infra/.env` (`gen-secrets.sh` does it; the demo file has a fake one).
2. Start the stack; `zalo` starts without a connector key and logs that it has none (it idles).
3. On the dashboard: Connectors > Thêm, name `zalo`. The key is shown ONCE.
4. Paste it into `infra/.env` as `ZALO_CONNECTOR_KEY=...`, then `docker compose -f infra/docker-compose.yml --env-file
   infra/.env up -d zalo`. Revoking the key on the Connectors page silences the connector at once.
5. Enter the Zalo accounts (bot token, personal login) on the Zalo pages. `ZALO_PUBLIC_URL` stays empty for long
   polling.

## Backups

`scripts/backup-postgres.sh`: a verified dump of `contete_agent` plus the globals, the agent's home `/data` (its secret
key) and the Zalo connector's `/data`, encrypted with age or gpg, with retention and an off-site hook. Plaintext is
refused unless `CONTETE_BACKUP_ALLOW_PLAINTEXT=true`. `scripts/restore-postgres.sh --verify|--restore` never overwrites
the live database or volumes. Nightly timer: `ubuntu/systemd/contete-backup.{service,timer}`.
