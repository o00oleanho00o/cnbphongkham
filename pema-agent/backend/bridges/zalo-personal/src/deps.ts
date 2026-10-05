import type { AccountManager } from "./account-registry.js";
import type { BridgeConfig } from "./config.js";
import type { QrLoginManager } from "./qr-login-manager.js";
import type { KillSwitch } from "./safety.js";
import type { HostLookup } from "./url-guard.js";

/** Everything the routes need, injected so tests build the app without zca-js or a network. */
export type AppDeps = {
  config: BridgeConfig;
  accounts: AccountManager;
  qr: QrLoginManager;
  killSwitch: KillSwitch;
  /** DNS lookup used by the `send-video` SSRF guard. */
  lookupHost: HostLookup;
};
