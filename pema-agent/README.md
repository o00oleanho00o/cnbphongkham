# pema-agent

CSKH (patient care) agent for Pema Digital Clinic. Two things in one code base:

1. a **Python derivative of [zalo-agent](https://github.com/vuhai2002/zalo-agent)** (MIT, TypeScript): Zalo
   channels, agent loop, persona, tools, memory, knowledge base, scheduler, MCP client, token accounting;
2. a **clinic CRM** (patient 360, appointments, care tasks, Inbox, review queue) and one Next.js frontend for
   both the CRM and the AI administration.

Zalo is the channel to the patient. This phase is text-only CSKH; image/video/document/web tools are ported but
switched off in the `patient_channel` policy profile. Every outgoing text to a patient is reviewed by a person
in that profile. All data in this repository is synthetic.

Start with [docs/PLAN-AI01.md](docs/PLAN-AI01.md) (goal, architecture, packages), then
[docs/CONTRACTS-AI01.md](docs/CONTRACTS-AI01.md) (interfaces, ownership, conventions) and
[docs/PORT-MAP.md](docs/PORT-MAP.md) (every zalo-agent file and where it goes in Python).
Licences of the upstream projects: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

```
Zalo -> webhook (FastAPI, role be_app) -> batcher -> Redis TurnQueue -> worker (role agent_worker)
                                                         |  agent loop, tools, policy hooks
Staff -> Next.js -> FastAPI (OpenAPI is the contract)    +-> ChannelPort.send_text (reviewed first in patient_channel)
Postgres: clinic.* (CRM, RLS) | clinic_agent.* (the agent's only door) | agent.* (engine, pgvector)
```

| Path | What |
|---|---|
| `backend/packages/contracts` | `pema_contracts`: DTOs, `ChannelPort`, the ports between packages, fakes |
| `backend/apps/api/pema` | the application: `channels`, `middleware`, `agent`, `conversation`, `knowledge`, `scheduler`, `mcp`, `documents`, `images`, `video`, `config`, `clinic`, `policy`, `api`, `workers`, `shared`, `core` |
| `backend/apps/api/alembic` | DDL: `0001` clinic, `0002` agent, `0003` clinic_agent |
| `backend/bridges/zalo-personal` | optional Node bridge around zca-js (placeholder until package C2) |
| `frontend` | OpenAPI type generation now; Next.js app in package E |
| `infra` | dev docker-compose (Postgres + pgvector, Redis), `.env.example` |
| `kb-samples`, `evals` | fictional knowledge documents; the 17 original eval scenarios + the CSKH set |
| `docs` | PLAN, CONTRACTS, PORT-MAP (SCOPE/SPEC/MODULEMAP/ARCH-AI01 come from package F) |

## Quick start

```
make setup        # uv sync --all-packages, pnpm install
make lint         # ruff, ruff format --check, pyright strict, import-linter
make test         # pytest (the DB tests need PEMA_TEST_DATABASE_URL, a throwaway Postgres)
make openapi      # backend/apps/api/openapi.json
make types        # frontend/src/lib/api/schema.d.ts from that file
cp infra/.env.example infra/.env   # edit the placeholders
make up           # Postgres + Redis
make db-upgrade   # ctx, clinic, clinic_agent, agent (reads infra/.env)
```

Without `make` (plain Windows), run the commands of each Makefile recipe directly. DB tests:

```
docker run -d --name pema-pg-test -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=pema \
    -p 127.0.0.1:55432:5432 pgvector/pgvector:pg17
PEMA_TEST_DATABASE_URL=postgresql+psycopg://postgres:testpw@127.0.0.1:55432/pema make test-db
```

## Rules that hold everywhere

* The agent side reaches the clinic only through `pema.clinic.actions` (import-linter), and in the database the
  `agent_worker` role has no privilege on `clinic.*` (views and functions of `clinic_agent` only).
* Every table has `clinic_id` and row level security; open work with `ClinicDatabase.session(clinic_id)`.
* Timestamps on the wire are ISO 8601 with `+07:00`. UI language is Vietnamese.
* Never commit `.env`, tokens, real phone numbers or names. No PII in logs (the logger redacts known keys).
* Zalo personal-account mode is off unless `PEMA_ZALO_PERSONAL_ENABLED` is set and a QR login was done; it risks
  a Zalo account lock (unofficial API).
