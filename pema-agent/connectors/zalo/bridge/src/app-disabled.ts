/**
 * The part of the app that exists whether or not the bridge is enabled: `GET /health`, the JSON 404 and
 * the JSON 500. Kept apart from `app.ts` so a DISABLED bridge boots without importing any route module
 * and therefore without loading zca-js at all.
 */
import { Hono } from "hono";
import type { BridgeConfig } from "./config.js";
import { fail, jsonResponse, ok, type AppEnv } from "./http.js";
import { createLogger, errorInfo } from "./logger.js";

const log = createLogger("app");

/** `GET /health` is the only unsigned route and returns nothing but these three fields. */
export function createBaseApp(config: BridgeConfig, activeAccounts: () => number): Hono<AppEnv> {
  const app = new Hono<AppEnv>();
  app.get("/health", () => ok({ enabled: config.enabled, accounts: activeAccounts() }));
  app.notFound(() => fail("bad_request", "Unknown route", { status: 404 }));
  app.onError((err) => {
    log.error(errorInfo(err), "Unhandled error");
    return jsonResponse(500, {
      ok: false,
      error: { kind: "transport", message: "Internal bridge error" },
    });
  });
  return app;
}

/** Every route except `GET /health` answers 503 `bridge_disabled`, signed or not. */
export function createDisabledApp(config: BridgeConfig): Hono<AppEnv> {
  const app = createBaseApp(config, () => 0);
  app.all("*", () => fail("bridge_disabled", "The zalo-personal bridge is disabled"));
  return app;
}
