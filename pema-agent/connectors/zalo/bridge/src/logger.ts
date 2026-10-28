// ported from: src/shared/logger.ts
// Deviations: no pino-pretty/pino-roll and no data dir (the bridge writes NOTHING to disk): JSON to
// stdout only. Redaction is added because this process handles credentials and message content:
// the keys below are censored even if a caller passes them by mistake. Callers still must not pass
// message text, names, phone numbers, cookies, QR images or the HMAC secret.
import pino, { type Logger } from "pino";

const REDACTED_KEYS = [
  "cookie",
  "cookies",
  "imei",
  "userAgent",
  "credential",
  "secret",
  "signature",
  "authorization",
  "text",
  "msg",
  "message",
  "content",
  "caption",
  "qr",
  "qr_png_base64",
  "qrBase64",
  "data_base64",
  "phone",
  "phoneNumber",
  "displayName",
  "zaloName",
];

/** Censor each key at depth 1 and 2 (`{ cookie }` and `{ credential: { cookie } }`). */
const REDACT_PATHS = REDACTED_KEYS.flatMap((key) => [key, `*.${key}`]);

const root = pino({
  level: process.env["ZALO_BRIDGE_LOG_LEVEL"] ?? "info",
  base: { service: "zalo-personal-bridge" },
  redact: { paths: REDACT_PATHS, censor: "[redacted]" },
});

export type { Logger };

export function createLogger(scope: string): Logger {
  return root.child({ scope });
}

/** Called once by the boot code with the configured level (and by tests with "silent"). */
export function setLogLevel(level: string): void {
  root.level = level;
}

/** Identity of an error that is safe to log: type and numeric code only, never the message. */
export function errorInfo(err: unknown): { errorName: string; code?: number } {
  const errorName = err instanceof Error ? err.name : typeof err;
  const code = (err as { code?: unknown } | null)?.code;
  return typeof code === "number" ? { errorName, code } : { errorName };
}
