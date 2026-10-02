# syntax=docker/dockerfile:1
# One image for the API, the worker and the one-shot migrate job (different command each).
# Build context: pema-agent/ (see docker-compose.yml). Ignore rules: api.Dockerfile.dockerignore.
#
# Stages: builder (uv resolves and installs the locked dependencies) -> runtime (no uv, no compiler, non-root).
#
# The lock must match the manifests: `uv sync --locked` FAILS the build when apps/api/pyproject.toml has
# dependencies that uv.lock does not (packages append libraries; regenerate uv.lock with `uv lock`). For a local
# build before the lock is regenerated: --build-arg UV_SYNC_FLAGS="" (re-resolves, not reproducible).
FROM python:3.12-slim-bookworm AS builder

ARG UV_SYNC_FLAGS="--locked"

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app/backend

# Layer 1: third-party dependencies only (cached until a manifest or the lock changes).
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
COPY backend/packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY backend/apps/api/pyproject.toml apps/api/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync ${UV_SYNC_FLAGS} --no-dev --no-install-workspace --package pema-api

# Layer 2: the workspace members themselves, installed non-editable so the runtime image needs no sources
# besides the Alembic files.
COPY backend/packages/contracts packages/contracts
COPY backend/apps/api/pema apps/api/pema
# --no-cache: uv keys the cached wheel of a local directory by its pyproject.toml, not by the sources, so a shared
# cache mount can hand back the wheel of an OLDER checkout (stale code in a fresh image). The third-party packages
# are already in /opt/venv from layer 1; only the two workspace members are built here.
RUN uv sync ${UV_SYNC_FLAGS} --no-cache --no-dev --no-editable --package pema-api


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PEMA_DATA_DIR=/var/lib/pema

# postgresql-client: psql for scripts/bootstrap-roles.sh (migrate job). Nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 pema \
    && useradd --system --uid 10001 --gid pema --home-dir /app --shell /usr/sbin/nologin pema \
    && mkdir -p /var/lib/pema /opt/pema/scripts \
    && chown -R pema:pema /var/lib/pema

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY backend/apps/api/alembic.ini apps/api/alembic.ini
COPY backend/apps/api/alembic apps/api/alembic
COPY infra/scripts/bootstrap-roles.sh infra/scripts/migrate.sh /opt/pema/scripts/
RUN sed -i 's/\r$//' /opt/pema/scripts/*.sh && chmod 0555 /opt/pema/scripts/*.sh

USER pema
EXPOSE 8000
VOLUME ["/var/lib/pema"]

CMD ["uvicorn", "--factory", "pema.bootstrap:create_app", "--host", "0.0.0.0", "--port", "8000"]
