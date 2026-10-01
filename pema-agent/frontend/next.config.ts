import { readFileSync } from "node:fs";

import type { NextConfig } from "next";

/**
 * The browser only ever talks to this origin; Next forwards `/api/*` to the backend so the session
 * cookie stays first-party (no CORS). Point PEMA_API_URL at the real API, or at `pnpm mock`
 * (http://127.0.0.1:4010) while the backend packages are still being built.
 *
 * `PEMA_API_INTERNAL_URL` (the compose network address of the api service, e.g. http://api:8000) wins over
 * `PEMA_API_URL`. Next.js evaluates `rewrites()` at BUILD time and bakes the result into the standalone
 * server, so this variable must be present when `next build` runs (a Docker build argument), not at runtime.
 */
const API_URL =
  process.env.PEMA_API_INTERNAL_URL ?? process.env.PEMA_API_URL ?? "http://127.0.0.1:8000";

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
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
      { source: "/healthz", destination: `${API_URL}/healthz` },
    ];
  },
};

export default config;
