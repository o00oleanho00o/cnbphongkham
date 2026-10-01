# syntax=docker/dockerfile:1
# Next.js dashboard (package E). Build context: pema-agent/. Ignore rules: frontend.Dockerfile.dockerignore.
#
# next.config.ts sets `output: "standalone"`, which the runtime stage copies (.next/standalone). The browser talks
# only to this server; it forwards /api/* to the API. Next.js bakes those rewrites at BUILD time, so the API
# address is the build argument PEMA_API_INTERNAL_URL (compose passes http://api:8000); changing it needs a rebuild.
FROM node:22-alpine AS deps
WORKDIR /app
ENV CI=true
RUN corepack enable
# pnpm-workspace.yaml holds the pnpm settings of this project (allowBuilds), so it travels with the lockfile
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
ARG PEMA_API_INTERNAL_URL=http://api:8000
ENV CI=true NEXT_TELEMETRY_DISABLED=1 PEMA_API_INTERNAL_URL=${PEMA_API_INTERNAL_URL}
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
# the OpenAPI file is the input of `pnpm run gen:types` (kept committed, so a build does not regenerate it)
COPY frontend/ ./
RUN mkdir -p public && pnpm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN addgroup --system --gid 10001 pema && adduser --system --uid 10001 --ingroup pema pema
COPY --from=builder --chown=pema:pema /app/public ./public
COPY --from=builder --chown=pema:pema /app/.next/standalone ./
COPY --from=builder --chown=pema:pema /app/.next/static ./.next/static
USER pema
EXPOSE 3000
CMD ["node", "server.js"]
