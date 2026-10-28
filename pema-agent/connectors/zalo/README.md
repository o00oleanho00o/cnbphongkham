# Zalo connector

Zalo for the Pema agent as a service of its own: Zalo Bot accounts, personal Zalo accounts (QR login through the Bun
bridge in `bridge/`) and, later, Official Accounts. It imports nothing from `backend/`. The only thing it shares with
the agent is the protocol in [docs/CONNECTOR-PROTOCOL.md](../../docs/CONNECTOR-PROTOCOL.md) (plan:
[docs/PLAN-zalo-service.md](../../docs/PLAN-zalo-service.md)).

```
Zalo  <->  zalo_connector (this service, :8089)  <->  agent (:8088, /v1/hooks/connectors/...)
              |-- SQLite KV   /data/zalo.db   (accounts, sealed tokens, contacts, outbox)
              |-- Bun bridge  /app/bridge     (personal accounts; run by this service on 127.0.0.1)
              `-- admin page  /ui/ + /v1/plugins/zalo/...   (the clinic web proxies /connectors/zalo/*)
```

## Run

```
uv sync
ZALO_SECRET_KEY=... CONNECTOR_KEY=... uv run python -m zalo_connector      # or: uv run zalo-connector
```

It listens on `0.0.0.0:8089`. `GET /ready` is open (container health check); `GET /health` is the protocol's signed
one.

## Getting `CONNECTOR_KEY`

On the clinic web: Điều khiển agent > Connectors > Thêm, name `zalo`. The key is shown **once**; paste it into
`CONNECTOR_KEY`. Revoking it there silences this service at once. Without it the service still runs (admin page,
polling) and keeps what it hears in its outbox, but cannot talk to the agent.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_URL` | `http://agent:8088` | The agent, as this service reaches it |
| `CALLBACK_URL` | `http://zalo:8089` | This service, as the agent reaches it (sent when a channel is registered) |
| `CONNECTOR_NAME` | `zalo` | Connector name; channels are `zalo` or `zalo-<account>` |
| `CONNECTOR_KEY` | | The key the agent issued (see above) |
| `ZALO_SECRET_KEY` | | Seals bot tokens and logins in the store (any string; Fernet key = sha256 of it). **Required**: the service refuses to start without it. Lose it and every stored token must be entered again |
| `ZALO_DATA_DIR` | `/data` | `zalo.db`, `bridge.log`, bridge install folder |
| `ZALO_BRIDGE_DIR` | `/app/bridge` | The Bun bridge with its `node_modules` (baked into the image) |
| `ZALO_UI_DIR` | `/app/ui/dist` | Built admin page, served under `/ui/` |
| `CRM_JWKS_URL` | | Public keys of the clinic web's SSO token; empty: admin routes answer 503 |
| `SSO_ISSUER` / `SSO_AUDIENCE` | `pema-clinic` / `pema-agent` | Claims the staff token must carry; its `scope` must hold `admin` |
| `PUBLIC_URL` | | https address Zalo reaches this service at (bot webhook = `<PUBLIC_URL>/v1/hooks/zalo/bot/<account>`); empty: bots long-poll |
| `RICH_TEXT` | `true` | Zalo bold/italic/lists on personal accounts; `false` sends plain text |
| `POLL_TIMEOUT_S` | `30` | How long one bot `getUpdates` waits (5-60) |
| `PORT` | `8089` | Listening port (also where the bridge posts its events, on loopback) |
| `PART_PAUSE_MIN_S` / `PART_PAUSE_MAX_S` | `10` / `20` | Random pause between the parts of one long reply (0 and 0: none); the parts go out in the background after `/send` answered |

## How it talks to the agent

- **In:** every message and observed event is written to the outbox in the store first, then pushed; retried 2 s,
  4 s ... up to 60 s until the agent answers 200; deleted only then; survives restarts. 404 re-registers the channel,
  401 is logged loudly and retried slowly. "Typing" is sent once and not kept.
- **Out:** `POST /send` gets the whole reply: cleaned (`format/`), checked for prompt leaks, split at the platform's
  limit, sent part by part; the same `delivery_id` sends once. `POST /typing`, `GET /health`. All signed with the key.
- **Channels:** every account that can run is registered as `zalo-<account>` with its `rules` text and
  `disabled_tools`, and unregistered when it stops.

## Layout

`main.py` app, `service.py` accounts/channels/bridge/jobs, `agent_client.py` registration + outbox,
`callback.py` `/send` `/typing` `/health`, `auth.py` signing + staff SSO, `routes.py` admin and webhook routes,
`store.py` + `seal.py` KV and sealing, `bot/` `personal/` `format/` `oa/` the Zalo code carried over from the plugin.
Licences of the carried-over code: `src/zalo_connector/NOTICE`.
