# syntax=docker/dockerfile:1
# crm-signer (apps/crm-signer): the only holder of the key that signs the agent's calls to the CRM gateway
# (docs/PLAN-crm-plugin.md 3.9). No database, no model, no plugin: a Starlette app, httpx and the key file.
# Build context: pema-agent/ (see docker-compose.yml). Ignore rules: crm-signer.Dockerfile.dockerignore.
#
# Stages: builder (uv installs the locked dependencies, then the package) -> runtime (non-root, read-only in compose).
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
# workspace the lock was made for (see api.Dockerfile).
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
COPY backend/packages/contracts/pyproject.toml packages/contracts/pyproject.toml
COPY backend/packages/agent-core/pyproject.toml packages/agent-core/pyproject.toml
COPY backend/packages/secret-cipher/pyproject.toml packages/secret-cipher/pyproject.toml
COPY backend/apps/api/pyproject.toml apps/api/pyproject.toml
COPY backend/apps/agent/pyproject.toml apps/agent/pyproject.toml
COPY backend/apps/crm-signer/pyproject.toml apps/crm-signer/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync ${UV_SYNC_FLAGS} --no-dev --no-install-workspace --package crm-signer

# Layer 2: the package itself (--no-cache: see api.Dockerfile).
COPY backend/apps/crm-signer/crm_signer apps/crm-signer/crm_signer
RUN uv sync ${UV_SYNC_FLAGS} --no-cache --no-dev --no-editable --package crm-signer


FROM python:3.12-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CRM_SIGNER_KEY_FILE=/keys/crm-signer-ed25519.pem

RUN groupadd --system --gid 10002 signer \
    && useradd --system --uid 10002 --gid signer --home-dir /app --shell /usr/sbin/nologin signer \
    && mkdir -p /keys \
    && chown signer:signer /keys

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
USER signer
EXPOSE 8090
VOLUME ["/keys"]

CMD ["crm-signer", "serve"]
