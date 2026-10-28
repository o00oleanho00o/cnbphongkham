# syntax=docker/dockerfile:1
# The Zalo connector (connectors/zalo): a standalone service that talks to the agent over the connector protocol
# (docs/CONNECTOR-PROTOCOL.md) and shares no code with backend/. It runs the Zalo clients (bot, OA, personal), serves
# its own admin pages to the clinic web, and starts the Bun bridge (zca-js) as a child process while a personal
# account needs it: the bridge's packages are installed here, so nobody installs it from the admin pages.
# Build context: pema-agent/connectors/zalo/ (see docker-compose.yml). Ignore rules: Dockerfile.dockerignore.
#
# Stages: bun -> ui (builds the admin pages' script), bridge (the bridge's production packages) ;
# builder (uv) -> runtime (non-root).
# The connector is installed non-editable: the runtime image carries the venv and the data, not the Python sources.

FROM oven/bun:1-slim AS bun


FROM bun AS ui
WORKDIR /build/ui
COPY ui/package.json ui/bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile
COPY ui ./
RUN bun run build


FROM bun AS bridge
WORKDIR /build/bridge
COPY bridge/package.json bridge/bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile --production
COPY bridge/tsconfig.json ./
COPY bridge/src src
COPY bridge/scripts scripts


FROM python:3.12-slim-bookworm AS builder

ARG UV_SYNC_FLAGS="--locked"

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app

# Layer 1: third-party dependencies only.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync ${UV_SYNC_FLAGS} --no-dev --no-install-project

# Layer 2: the connector itself, non-editable (the venv holds it).
COPY README.md ./
COPY src src
RUN uv sync ${UV_SYNC_FLAGS} --no-cache --no-dev --no-editable


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ZALO_BRIDGE_DIR=/app/bridge \
    ZALO_UI_DIR=/app/ui/dist \
    ZALO_DATA_DIR=/data

COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun

RUN groupadd --system --gid 10001 zalo \
    && useradd --system --uid 10001 --gid zalo --home-dir /home/zalo --create-home --shell /usr/sbin/nologin zalo \
    && mkdir -p /data \
    && chown zalo:zalo /data

COPY --from=builder /opt/venv /opt/venv
COPY --from=bridge /build/bridge /app/bridge
COPY --from=ui /build/ui/dist /app/ui/dist

USER zalo
WORKDIR /app
EXPOSE 8089
VOLUME ["/data"]

CMD ["python", "-m", "zalo_connector"]
