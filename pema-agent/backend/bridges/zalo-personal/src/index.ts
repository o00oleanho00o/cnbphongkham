/**
 * Boot of the bridge.
 *
 * - Refuses to start when enabled without a secret of at least 16 characters.
 * - Disabled (the code default): serves only `GET /health` and 503 for the rest; zca-js is never loaded.
 * - Enabled: nothing logs in until the API calls `/start` or an operator scans a QR code.
 *
 * Run it with `pnpm start` (tsx).
 */
import { serve } from "@hono/node-server";
import { ConfigError, loadConfig, type BridgeConfig } from "./config.js";
import { createLogger, setLogLevel } from "./logger.js";

const log = createLogger("boot");

function loadConfigOrExit(): BridgeConfig {
  try {
    return loadConfig(process.env);
  } catch (err) {
    // ConfigError messages never contain a value, only the name of the setting.
    log.fatal(
      { reason: err instanceof ConfigError ? err.message : "invalid configuration" },
      "Cannot start",
    );
    process.exit(1);
  }
}

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);

async function main(): Promise<void> {
  const config = loadConfigOrExit();
  setLogLevel(config.logLevel);

  if (!LOOPBACK_HOSTS.has(config.host)) {
    log.warn(
      { host: config.host },
      "The bridge is not bound to loopback: keep it off any public network",
    );
  }

  if (!config.enabled) {
    const { createDisabledApp } = await import("./app-disabled.js");
    serve({ fetch: createDisabledApp(config).fetch, hostname: config.host, port: config.port });
    log.warn({ port: config.port }, "PEMA_ZALO_PERSONAL_ENABLED is false: only /health is served");
    return;
  }

  const [{ createBridge }, { createZcaGateway }, { HttpEventPublisher }] = await Promise.all([
    import("./bridge.js"),
    import("./zalo-client.js"),
    import("./event-publisher.js"),
  ]);
  const publisher = new HttpEventPublisher({
    secret: config.secret,
    apiBaseUrl: config.apiBaseUrl,
  });
  const bridge = createBridge({ config, gateway: createZcaGateway(), publisher });
  const server = serve({ fetch: bridge.app.fetch, hostname: config.host, port: config.port });
  log.info(
    { host: config.host, port: config.port },
    "zalo-personal bridge listening (no account is running)",
  );

  const shutdown = (signal: string): void => {
    log.warn({ signal }, "Shutting down: stopping every account");
    void bridge.accounts
      .stopAll()
      .then(() => publisher.flush())
      .finally(() => {
        server.close();
        process.exit(0);
      });
  };
  process.once("SIGINT", () => shutdown("SIGINT"));
  process.once("SIGTERM", () => shutdown("SIGTERM"));
}

void main();
