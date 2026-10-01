# syntax=docker/dockerfile:1
# Next.js dashboard (package E). Build context: pema-agent/. Ignore rules: frontend.Dockerfile.dockerignore.
#
# DEPENDS ON PACKAGE E. Until frontend/ holds a Next.js app this build fails at `pnpm run build` (package A
# only ships the OpenAPI type generator). Package E must also set `output: "standalone"` in next.config.*,
# because the runtime stage copies .next/standalone. The server reads PEMA_API_INTERNAL_URL at runtime.
FROM node:22-alpine AS deps
WORKDIR /app
ENV CI=true
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
ENV CI=true NEXT_TELEMETRY_DISABLED=1
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
