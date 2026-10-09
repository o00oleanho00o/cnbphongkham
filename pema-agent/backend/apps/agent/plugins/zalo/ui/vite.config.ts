import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// One script the dashboard loads (`[ui] entry`); React is the dashboard's, never bundled twice.
export default defineConfig({
  plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    lib: { entry: "src/main.tsx", formats: ["iife"], name: "pemaZalo", fileName: () => "client.js" },
    rolldownOptions: {
      external: ["react", "react/jsx-runtime"],
      output: {
        globals: { react: "__PEMA_AGENT__.React", "react/jsx-runtime": "__PEMA_AGENT__.jsxRuntime" },
      },
    },
  },
  test: { environment: "node" },
});
