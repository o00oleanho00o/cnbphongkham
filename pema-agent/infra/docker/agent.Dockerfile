# syntax=docker/dockerfile:1
# The general agent (apps/agent): gateway, dashboard (plugin web), bundled plugins, and Node + pnpm for the plugins'
# helper processes. The Zalo bridge's packages are installed here, in the plugin's own `bridge` folder, so the bridge
# is ready from the start (nobody installs it from the dashboard); it runs only while a personal account needs it.
# Build context: pema-agent/ (see docker-compose.yml). Ignore rules: agent.Dockerfile.dockerignore.
#
# Stages: node (Node 22 + pnpm) -> ui (builds the plugins' browser halves), bridge (the Zalo bridge's production
# packages) ; builder (uv) -> runtime (non-root).
# The agent app is installed editable on purpose: it finds its bundled plugins next to its package folder.

FROM node:22-bookworm-slim AS node
RUN npm install -g pnpm@11.17.0 && pnpm --version


FROM node AS ui
WORKDIR /build/plugins
COPY backend/apps/agent/plugins/web/ui/package.json backend/apps/agent/plugins/web/ui/pnpm-lock.yaml web/ui/
COPY backend/apps/agent/plugins/zalo/ui/package.json backend/apps/agent/plugins/zalo/ui/pnpm-lock.yaml zalo/ui/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    cd web/ui && pnpm install --frozen-lockfile \
    && cd ../../zalo/ui && pnpm install --frozen-lockfile
COPY backend/apps/agent/plugins/web/ui web/ui
COPY backend/apps/agent/plugins/zalo/ui zalo/ui
# zalo first: the dashboard's stylesheet scans the other plugins' sources, the zalo build reads the SDK types.
RUN cd zalo/ui && pnpm run build && cd ../../web/ui && pnpm run build


FROM node AS bridge
WORKDIR /build/bridge
COPY backend/apps/agent/plugins/zalo/bridge/package.json backend/apps/agent/plugins/zalo/bridge/pnpm-lock.yaml backend/apps/agent/plugins/zalo/bridge/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store     pnpm install --frozen-lockfile --prod


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

COPY --from=node /usr/local/bin/ /usr/local/bin/
COPY --from=node /usr/local/lib/node_modules/ /usr/local/lib/node_modules/

RUN groupadd --system --gid 10001 agent \
    && useradd --system --uid 10001 --gid agent --home-dir /home/agent --create-home --shell /usr/sbin/nologin agent \
    && mkdir -p /data \
    && chown agent:agent /data

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/backend/packages/agent-core /app/backend/packages/agent-core
COPY --from=builder /app/backend/packages/secret-cipher /app/backend/packages/secret-cipher
COPY --from=builder /app/backend/apps/agent /app/backend/apps/agent
COPY --from=ui /build/plugins/web/ui/dist /app/backend/apps/agent/plugins/web/ui/dist
COPY --from=ui /build/plugins/zalo/ui/dist /app/backend/apps/agent/plugins/zalo/ui/dist
COPY --from=bridge /build/bridge/node_modules /app/backend/apps/agent/plugins/zalo/bridge/node_modules

USER agent
WORKDIR /app/backend/apps/agent
EXPOSE 8088
VOLUME ["/data"]

CMD ["agent", "serve", "--profile", "agents/dev", "--home", "/data", "--host", "0.0.0.0", "--port", "8088"]
