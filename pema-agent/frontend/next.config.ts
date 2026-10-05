import { readFileSync } from "node:fs";

import type { NextConfig } from "next";

/**
 * The browser only ever talks to this origin. `/api/v1/**` and `/healthz` are forwarded to the backend by the
 * route handlers `src/app/api/[...path]/route.ts` and `src/app/healthz/route.ts` (logic in
 * `src/lib/server/api-proxy.ts`), which read `PEMA_API_INTERNAL_URL` (or `PEMA_API_URL`, for `pnpm dev` and
 * `pnpm dev:mock`) on EVERY request. This replaces `rewrites()`: Next.js evaluates `rewrites()` at build time
 * and bakes the result into the standalone server, which made the API address a Docker build argument. Now
 * one image runs against any API address, set when the container starts. The session cookie stays
 * first-party (no CORS).
 */

/**
 * Version LẤY TỪ package.json, không gõ tay trong JSX (bản gốc làm vậy qua `__APP_VERSION__` của
 * Vite): nâng package.json lên là sidebar hiện đúng số mới.
 */
const version = (
  JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as {
    version: string;
  }
).version;

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // `next dev` would otherwise write AGENTS.md and CLAUDE.md next to the app; the repo has its own rules.
  agentRules: false,
  devIndicators: false,
  env: { NEXT_PUBLIC_APP_VERSION: version },
};

export default config;
