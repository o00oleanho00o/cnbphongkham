# infra

Package A ships only `docker-compose.yml` (Postgres 17 + pgvector, Redis) and `.env.example`, enough to
run and test the DDL. Package F extends them: api, worker, bridge and ollama services, the role bootstrap,
and the Ubuntu-native guide (NVIDIA driver, Ollama/llama-server, Docker, Tailscale).

```
cp .env.example .env     # edit the placeholders; never commit .env
docker compose --env-file .env up -d
```

Migrations run as the owner role; the roles `be_app` and `agent_worker` are created by the first alembic
migration (NOLOGIN unless `PEMA_BE_APP_PASSWORD` / `PEMA_AGENT_WORKER_PASSWORD` are set).
