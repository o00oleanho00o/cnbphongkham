import { readFileSync } from "node:fs";

import tailwindcss from "@tailwindcss/vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { nitro } from "nitro/vite";
import { defineConfig } from "vite";

/** Version LẤY TỪ package.json, không gõ tay trong JSX: nâng package.json lên là sidebar hiện đúng số mới. */
const { version } = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf8"),
) as {
  version: string;
};

/**
 * The browser only ever talks to this origin. `/api/v1/**`, `/agent/**` and `/healthz` are server routes
 * (`src/routes/{api,agent}/$.ts`, `src/routes/healthz.ts`) that read `PEMA_API_INTERNAL_URL` (or `PEMA_API_URL`)
 * on EVERY request, so one image runs against any API address, set when the container starts.
 * `bun run build` writes the production server to `.output/` (Nitro, preset bun): `bun .output/server/index.mjs`.
 */
export default defineConfig({
  server: { port: 3000 },
  resolve: { tsconfigPaths: true },
  define: { "import.meta.env.VITE_APP_VERSION": JSON.stringify(version) },
  plugins: [tailwindcss(), tanstackStart(), nitro({ preset: "bun" }), viteReact()],
});
