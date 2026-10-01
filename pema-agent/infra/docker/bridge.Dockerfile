# syntax=docker/dockerfile:1
# Node bridge around zca-js for the personal-account Zalo channel (package C2). Build context: pema-agent/.
# Ignore rules: bridge.Dockerfile.dockerignore.
#
# DEPENDS ON PACKAGE C2. backend/bridges/zalo-personal holds only a README until C2 adds package.json,
# pnpm-lock.yaml and the sources; this build fails at the COPY below until then. C2 must provide the scripts
# `build` and `start` (the entry point is C2's choice, which is why the CMD calls `pnpm start`).
#
# RISK: zca-js is an unofficial client of the personal Zalo account; the account can be locked. The service is
# in a compose profile (`bridge`) that is OFF by default and is never published to the host.
FROM node:22-alpine AS deps
WORKDIR /app
ENV CI=true
RUN corepack enable
COPY backend/bridges/zalo-personal/package.json backend/bridges/zalo-personal/pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM node:22-alpine AS builder
WORKDIR /app
ENV CI=true
RUN corepack enable
COPY --from=deps /app/node_modules ./node_modules
COPY backend/bridges/zalo-personal/ ./
RUN pnpm run build && pnpm prune --prod

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=8200
RUN corepack enable \
    && addgroup --system --gid 10001 pema && adduser --system --uid 10001 --ingroup pema pema
COPY --from=builder --chown=pema:pema /app ./
USER pema
EXPOSE 8200
CMD ["pnpm", "start"]
