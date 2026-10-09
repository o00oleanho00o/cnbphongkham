/**
 * The Hono application of the bridge.
 *
 * New module (no TS original: the original had no HTTP surface for zca-js). `GET /health` is the only
 * unsigned route. When the bridge is disabled every other route answers 503 `bridge_disabled` and no
 * dependency (so no zca-js) is ever touched. When enabled, every route under `/v1` needs a valid HMAC
 * (see `auth.ts`).
 */
import { Hono, type MiddlewareHandler } from "hono";
import { bodyLimit } from "hono/body-limit";
import { SIGNATURE_HEADER, TIMESTAMP_HEADER, verifySignature } from "./auth.js";
import type { BridgeConfig } from "./config.js";
import { createBaseApp, createDisabledApp } from "./app-disabled.js";
import type { AppDeps } from "./deps.js";
import { fail, type AppEnv } from "./http.js";
import { createLogger } from "./logger.js";
import { accountRoutes } from "./routes-accounts.js";
import { directoryRoutes } from "./routes-directory.js";
import { messagingRoutes } from "./routes-messaging.js";

const log = createLogger("app");

/** Largest request body: a 10 MB attachment is ~13.4 MB as base64. */
export const MAX_BODY_BYTES = 16 * 1024 * 1024;

function hmacMiddleware(secret: string, clock: () => number): MiddlewareHandler<AppEnv> {
  return async (c, next) => {
    const rawBody = new Uint8Array(await c.req.arrayBuffer());
    const result = verifySignature({
      secret,
      timestamp: c.req.header(TIMESTAMP_HEADER),
      signature: c.req.header(SIGNATURE_HEADER),
      body: rawBody,
      nowSeconds: Math.floor(clock() / 1000),
    });
    if (!result.ok) {
      log.warn({ reason: result.reason }, "Request refused: bad signature");
      return fail("unauthorized", "Missing or invalid signature");
    }
    c.set("rawBody", rawBody);
    await next();
  };
}

/**
 * `deps` is required when `config.enabled`; a disabled bridge passes none, so nothing that could reach
 * Zalo exists in that process.
 */
export function createApp(
  config: BridgeConfig,
  deps?: AppDeps,
  clock: () => number = () => Date.now(),
): Hono<AppEnv> {
  if (!config.enabled || !deps) return createDisabledApp(config);

  const app = createBaseApp(config, () => deps.accounts.activeCount());

  app.use(
    "/v1/*",
    bodyLimit({
      maxSize: MAX_BODY_BYTES,
      onError: () => fail("bad_request", "Body too large", { status: 413 }),
    }),
  );
  app.use("/v1/*", hmacMiddleware(config.secret, clock));
  app.route("/v1", accountRoutes(deps));
  app.route("/v1", messagingRoutes(deps));
  app.route("/v1", directoryRoutes(deps));
  return app;
}
