# syntax=docker/dockerfile:1
# Next.js dashboard (package E). Build context: pema-agent/. Ignore rules: frontend.Dockerfile.dockerignore.
#
# next.config.ts sets `output: "standalone"`, which the runtime stage copies (.next/standalone). The browser talks
# only to this server; its route handlers (src/app/api/[...path], src/app/healthz) forward /api/v1 and /healthz to
# the API. The API address is NOT part of the image: the handlers read the environment variable
# PEMA_API_INTERNAL_URL on every request (compose passes http://api:8000), so the same image runs against any
# address, set with `docker run -e` or `environment:`. Unset, it falls back to PEMA_API_URL, then 127.0.0.1:8000.
#
# The build keeps the pema-agent/ layout (frontend/ next to backend/): globals.css scans the agent plugins' page
# sources (backend/apps/agent/plugins/*/ui/src, the only part of backend/ the ignore file lets in) and Turbopack's
# root is pema-agent/, so the standalone server sits in frontend/.
FROM node:22-alpine AS deps
WORKDIR /app/frontend
ENV CI=true
RUN corepack enable
# pnpm-workspace.yaml holds the pnpm settings of this project (allowBuilds), so it travels with the lockfile
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app/frontend
ENV CI=true NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
COPY --from=deps /app/frontend/node_modules ./node_modules
COPY backend/apps/agent/plugins /app/backend/apps/agent/plugins
# the OpenAPI file is the input of `pnpm run gen:types` (kept committed, so a build does not regenerate it)
COPY frontend/ ./
RUN mkdir -p public && pnpm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup --system --gid 10001 pema && adduser --system --uid 10001 --ingroup pema pema
COPY --from=builder --chown=pema:pema /app/frontend/.next/standalone ./
COPY --from=builder --chown=pema:pema /app/frontend/public ./frontend/public
COPY --from=builder --chown=pema:pema /app/frontend/.next/static ./frontend/.next/static
USER pema
EXPOSE 3000
CMD ["node", "frontend/server.js"]
