import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `pnpm dev` serves this app at /ui/web/ and sends the API and the other plugins' files to a local `agent serve`.
const AGENT = "http://127.0.0.1:8088";

export default defineConfig({
  base: "/ui/web/",
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/v1": AGENT,
      "^/ui/(?!web/)": AGENT,
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
  test: { environment: "node" },
});
