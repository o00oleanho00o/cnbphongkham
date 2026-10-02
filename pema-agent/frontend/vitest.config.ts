import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    // `.test.tsx` files (screens) opt into jsdom with `// @vitest-environment jsdom` on their first line.
    include: ["src/**/*.test.{ts,tsx}", "mock/**/*.test.ts"],
    environment: "node",
    testTimeout: 60_000,
  },
});
