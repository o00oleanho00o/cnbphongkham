import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    // Screens and the mock are checked end to end (`e2e/`), not by unit tests; only the server-side proxies keep some.
    include: ["src/lib/server/**/*.test.ts"],
    environment: "node",
    testTimeout: 60_000,
  },
});
