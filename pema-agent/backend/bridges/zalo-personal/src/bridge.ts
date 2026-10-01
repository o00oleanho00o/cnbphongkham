/**
 * Wiring of the bridge: one place that builds the managers and the app from a gateway and a publisher.
 * `index.ts` calls it with the real zca-js gateway and the HTTP publisher; tests call it with fakes.
 */
import type { Hono } from "hono";
import { AccountManager } from "./account-registry.js";
import { createApp } from "./app.js";
import type { BridgeConfig } from "./config.js";
import type { EventPublisher } from "./event-publisher.js";
import type { AppEnv } from "./http.js";
import { QrLoginManager } from "./qr-login-manager.js";
import { KillSwitch } from "./safety.js";
import { lookupAddresses, type HostLookup } from "./url-guard.js";
import type { Gateway } from "./zalo-types.js";

export type Bridge = {
  app: Hono<AppEnv>;
  accounts: AccountManager;
  qr: QrLoginManager;
  killSwitch: KillSwitch;
};

export type BridgeOptions = {
  config: BridgeConfig;
  gateway: Gateway;
  publisher: EventPublisher;
  now?: () => number;
  lookupHost?: HostLookup;
};

export function createBridge(options: BridgeOptions): Bridge {
  const { config, gateway, publisher } = options;
  const now = options.now ?? (() => Date.now());
  const killSwitch = new KillSwitch();
  const accounts = new AccountManager({ config, gateway, publisher, now });
  const qr = new QrLoginManager({
    login: (_accountId, onEvent, signal) => gateway.loginQR(onEvent, signal),
    attach: (accountId, clinicSlug, session) =>
      accounts.attachFromQr(accountId, clinicSlug, session),
    stopAccount: (accountId) => accounts.stop(accountId),
    now,
  });
  const app = createApp(
    config,
    { config, accounts, qr, killSwitch, lookupHost: options.lookupHost ?? lookupAddresses },
    now,
  );
  return { app, accounts, qr, killSwitch };
}
