// End-to-end tests of the dashboard against a RUNNING stack (the clinic web at E2E_BASE_URL, which reaches the
// agent through its `/agent` proxy). They replace the unit tests of the screens: a screen is proven by opening it
// in a real browser and doing what an admin does. The Chrome installed on the machine is used (no download).
//
//   E2E_EMAIL=... E2E_PASSWORD=... bun run e2e        (the owner account of the stack under test)
//   E2E_BASE_URL=http://localhost:3000                 where the web listens (default)
//   E2E_ALLOW_SEND=1                                   lets the test that writes to a real customer chat run
import { defineConfig } from "playwright/test";

export default defineConfig({
  testDir: ".",
  testMatch: "*.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    channel: "chrome",
    locale: "vi-VN",
    timezoneId: "Asia/Ho_Chi_Minh",
    viewport: { width: 1280, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  outputDir: "../test-results",
});
