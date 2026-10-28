# syntax=docker/dockerfile:1
# The general agent (apps/agent): gateway, dashboard (plugin web) and bundled plugins. No Bun in the runtime
# image: chat platforms (Zalo ...) are separate connector services that plug in through the `connectors` plugin.
# Build context: pema-agent/ (see docker-compose.yml). Ignore rules: agent.Dockerfile.dockerignore.
#
# Stages: bun -> ui (builds the plugins' browser halves; bun is only here); builder (uv) -> runtime (non-root).
# The agent app is installed editable on purpose: it finds its bundled plugins next to its package folder.

FROM oven/bun:1-slim AS bun


FROM bun AS ui
WORKDIR /build/plugins
COPY backend/apps/agent/plugins/web/ui/package.json backend/apps/agent/plugins/web/ui/bun.lock web/ui/
COPY backend/apps/agent/plugins/knowledge/ui/package.json backend/apps/agent/plugins/knowledge/ui/bun.lock knowledge/ui/
COPY backend/apps/agent/plugins/skills/ui/package.json backend/apps/agent/plugins/skills/ui/bun.lock skills/ui/
COPY backend/apps/agent/plugins/conversations/ui/package.json backend/apps/agent/plugins/conversations/ui/bun.lock conversations/ui/
COPY backend/apps/agent/plugins/jev/ui/package.json backend/apps/agent/plugins/jev/ui/bun.lock jev/ui/
COPY backend/apps/agent/plugins/connectors/ui/package.json backend/apps/agent/plugins/connectors/ui/bun.lock connectors/ui/
RUN --mount=type=cache,target=/root/.bun/install/cache \
    cd web/ui && bun install --frozen-lockfile \
    && cd ../../knowledge/ui && bun install --frozen-lockfile \
    && cd ../../skills/ui && bun install --frozen-lockfile \
    && cd ../../conversations/ui && bun install --frozen-lockfile \
    && cd ../../jev/ui && bun install --frozen-lockfile \
    && cd ../../connectors/ui && bun install --frozen-lockfile
COPY backend/apps/agent/plugins/web/ui web/ui
COPY backend/apps/agent/plugins/knowledge/ui knowledge/ui
COPY backend/apps/agent/plugins/skills/ui skills/ui
COPY backend/apps/agent/plugins/conversations/ui conversations/ui
COPY backend/apps/agent/plugins/jev/ui jev/ui
COPY backend/apps/agent/plugins/connectors/ui connectors/ui
# plugins first: the dashboard's stylesheet scans the other plugins' sources, their builds read the SDK types.
RUN cd knowledge/ui && bun run build && cd ../../skills/ui && bun run build \
    && cd ../../conversations/ui && bun run build \
    && cd ../../jev/ui && bun run build \
    && cd ../../connectors/ui && bun run build \
    && cd ../../web/ui && bun run build


FROM python:3.12-slim-bookworm AS builder

ARG UV_SYNC_FLAGS="--locked"

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app/backend

# Layer 1: third-party dependencies only. Every workspace member's manifest is copied so `--locked` sees the
# workspace the lock was made for.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
COPY backend/packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY backend/packages/agent-core/pyproject.toml packages/agent-core/pyproject.toml
COPY backend/packages/secret-cipher/pyproject.toml packages/secret-cipher/pyproject.toml
COPY backend/apps/api/pyproject.toml apps/api/pyproject.toml
COPY backend/apps/agent/pyproject.toml apps/agent/pyproject.toml
COPY backend/apps/crm-signer/pyproject.toml apps/crm-signer/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync ${UV_SYNC_FLAGS} --no-dev --no-install-workspace --package agent-app

# Layer 2: the workspace members, editable (the runtime image keeps these sources at the same paths).
COPY backend/packages/agent-core packages/agent-core
COPY backend/packages/secret-cipher packages/secret-cipher
COPY backend/apps/agent apps/agent
RUN uv sync ${UV_SYNC_FLAGS} --no-cache --no-dev --package agent-app


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1


RUN groupadd --system --gid 10001 agent \
    && useradd --system --uid 10001 --gid agent --home-dir /home/agent --create-home --shell /usr/sbin/nologin agent \
    && mkdir -p /data \
    && chown agent:agent /data

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/backend/packages/agent-core /app/backend/packages/agent-core
COPY --from=builder /app/backend/packages/secret-cipher /app/backend/packages/secret-cipher
COPY --from=builder /app/backend/apps/agent /app/backend/apps/agent
COPY --from=ui /build/plugins/web/ui/dist /app/backend/apps/agent/plugins/web/ui/dist
COPY --from=ui /build/plugins/knowledge/ui/dist /app/backend/apps/agent/plugins/knowledge/ui/dist
COPY --from=ui /build/plugins/skills/ui/dist /app/backend/apps/agent/plugins/skills/ui/dist
COPY --from=ui /build/plugins/conversations/ui/dist /app/backend/apps/agent/plugins/conversations/ui/dist
COPY --from=ui /build/plugins/jev/ui/dist /app/backend/apps/agent/plugins/jev/ui/dist
COPY --from=ui /build/plugins/connectors/ui/dist /app/backend/apps/agent/plugins/connectors/ui/dist

USER agent
WORKDIR /app/backend/apps/agent
EXPOSE 8088
VOLUME ["/data"]

CMD ["agent", "serve", "--profile", "agents/dev", "--home", "/data", "--host", "0.0.0.0", "--port", "8088"]
