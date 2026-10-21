# syntax=docker/dockerfile:1
# TanStack Start dashboard (package E), built by Vite and run by bun. Build context: pema-agent/. Ignore rules:
# frontend.Dockerfile.dockerignore.
#
# `bun run build` writes a self-contained Nitro server to .output/ (vite.config.ts, preset bun), which the runtime stage
# copies. The browser talks only to this server; its server routes (src/routes/api/$.ts, src/routes/agent/$.ts,
# src/routes/healthz.ts) forward /api/v1, /agent and /healthz to the API and the agent. The API address is NOT part of
# the image: the handlers read the environment variable PEMA_API_INTERNAL_URL on every request (compose passes
# http://api:8000), so the same image runs against any address, set with `docker run -e` or `environment:`. Unset, it
# falls back to PEMA_API_URL, then 127.0.0.1:8000.
#
# The build keeps the pema-agent/ layout (frontend/ next to backend/): globals.css scans the agent plugins' page
# sources (backend/apps/agent/plugins/*/ui/src, the only part of backend/ the ignore file lets in).
FROM oven/bun:1-alpine AS deps
WORKDIR /app/frontend
COPY frontend/package.json frontend/bun.lock ./
RUN --mount=type=cache,target=/root/.bun/install/cache \
    bun install --frozen-lockfile

FROM oven/bun:1-alpine AS builder
WORKDIR /app/frontend
COPY --from=deps /app/frontend/node_modules ./node_modules
COPY backend/apps/agent/plugins /app/backend/apps/agent/plugins
# the OpenAPI file is the input of `bun run gen:types` (kept committed, so a build does not regenerate it)
COPY frontend/ ./
RUN mkdir -p public && bun run build

FROM oven/bun:1-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOST=0.0.0.0
RUN addgroup --system --gid 10001 pema && adduser --system --uid 10001 --ingroup pema pema
COPY --from=builder --chown=pema:pema /app/frontend/.output ./.output
USER pema
EXPOSE 3000
CMD ["bun", ".output/server/index.mjs"]
