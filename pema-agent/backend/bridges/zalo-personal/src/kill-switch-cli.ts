/**
 * Logic of `pnpm kill-switch`: sign and send `POST/GET /v1/kill-switch` to the bridge.
 *
 * New module (no TS original). The emergency stop must work even when the API and the admin UI do not,
 * so it talks to the bridge directly with the same HMAC the API uses. The CLI entry is
 * `scripts/kill-switch.ts`; the logic lives here so it is tested.
 */
import { signedHeaders } from "./auth.js";

export type KillSwitchCommand =
  | { action: "on"; scope: "proactive" | "all"; reason?: string }
  | { action: "off" }
  | { action: "status" };

export const USAGE =
  "Usage: pnpm kill-switch <on|off|status> [--scope all|proactive] [--reason <text>]\n" +
  "Reads PEMA_ZALO_BRIDGE_SECRET (required), PEMA_ZALO_BRIDGE_HOST and PEMA_ZALO_BRIDGE_PORT from the environment or .env.";

function readOption(args: readonly string[], name: string): string | undefined {
  const index = args.indexOf(name);
  return index === -1 ? undefined : args[index + 1];
}

/** Returns the command, or an error text to show with the usage. */
export function parseKillSwitchArgs(
  args: readonly string[],
): KillSwitchCommand | { error: string } {
  const action = args[0];
  if (action === "status") return { action: "status" };
  if (action === "off") return { action: "off" };
  if (action !== "on") return { error: "Expected on, off or status" };
  const scope = readOption(args, "--scope") ?? "all";
  if (scope !== "all" && scope !== "proactive")
    return { error: "--scope must be all or proactive" };
  const reason = readOption(args, "--reason");
  return { action: "on", scope, ...(reason ? { reason } : {}) };
}

export type KillSwitchEnv = Readonly<Record<string, string | undefined>>;

export type KillSwitchResult = { ok: boolean; status: number; body: string };

/** Sign and send the command. Never prints or returns the secret. */
export async function sendKillSwitch(
  command: KillSwitchCommand,
  env: KillSwitchEnv,
  fetchImpl: typeof fetch = fetch,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): Promise<KillSwitchResult> {
  const secret = env["PEMA_ZALO_BRIDGE_SECRET"] ?? "";
  if (!secret) throw new Error("PEMA_ZALO_BRIDGE_SECRET is not set");
  const host = env["PEMA_ZALO_BRIDGE_HOST"] || "127.0.0.1";
  const port = env["PEMA_ZALO_BRIDGE_PORT"] || "8200";
  const url = `http://${host.includes(":") ? `[${host}]` : host}:${port}/v1/kill-switch`;

  const isStatus = command.action === "status";
  const body = isStatus
    ? ""
    : JSON.stringify(
        command.action === "off"
          ? { on: false }
          : {
              on: true,
              scope: command.scope,
              ...(command.reason ? { reason: command.reason } : {}),
            },
      );
  const response = await fetchImpl(url, {
    method: isStatus ? "GET" : "POST",
    headers: {
      ...(isStatus ? {} : { "content-type": "application/json" }),
      ...signedHeaders(secret, body, nowSeconds),
    },
    ...(isStatus ? {} : { body }),
    signal: AbortSignal.timeout(10_000),
  });
  return { ok: response.ok, status: response.status, body: await response.text() };
}
