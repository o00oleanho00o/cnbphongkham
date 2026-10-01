# syntax=docker/dockerfile:1
# Node bridge around zca-js for the personal-account Zalo channel (package C2). Build context: pema-agent/.
# Ignore rules: bridge.Dockerfile.dockerignore.
#
# There is no build step on purpose: the bridge is TypeScript that runs through tsx (the same entry point as
# `pnpm start` in development), and tsx is a runtime dependency in package.json for that reason. Production
# installs only `dependencies` (`--prod`), so eslint, tsc and prettier are not in the image.
#
# RISK: zca-js is an unofficial client of the personal Zalo account; the account can be locked. The service is
# in a compose profile (`bridge`) that is OFF by default and is never published to the host.
FROM node:22-alpine AS deps
WORKDIR /app
ENV CI=true
RUN corepack enable
# pnpm-workspace.yaml holds the pnpm settings of this project (allowBuilds), so it travels with the lockfile
COPY backend/bridges/zalo-personal/package.json backend/bridges/zalo-personal/pnpm-lock.yaml backend/bridges/zalo-personal/pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prod

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production PEMA_ZALO_BRIDGE_PORT=8200
RUN addgroup --system --gid 10001 pema && adduser --system --uid 10001 --ingroup pema pema
COPY --from=deps --chown=pema:pema /app/node_modules ./node_modules
COPY --chown=pema:pema backend/bridges/zalo-personal/package.json backend/bridges/zalo-personal/tsconfig.json ./
COPY --chown=pema:pema backend/bridges/zalo-personal/src ./src
COPY --chown=pema:pema backend/bridges/zalo-personal/scripts ./scripts
USER pema
EXPOSE 8200
# Same command as the `start` script, without a package manager in the runtime stage.
CMD ["node_modules/.bin/tsx", "src/index.ts"]
