/**
 * Cấu hình của bridge, đọc MỘT lần từ biến môi trường lúc boot.
 *
 * New module (no TS original): the original ran in-process and read `env.ts`; the bridge is a separate
 * process, so it has its own small set of variables (see README, "Protocol").
 */

export type BridgeConfig = {
  /** Mặc định TẮT trong code. Tắt = mọi route trừ GET /health trả 503, zca-js không bao giờ được tạo. */
  enabled: boolean;
  /** HMAC secret dùng chung với API. Bắt buộc khi `enabled`. */
  secret: string;
  host: string;
  port: number;
  /** Gốc URL API; sự kiện được POST tới `{apiBaseUrl}/webhooks/zalo-bridge/{clinic_slug}/{account_id}`. */
  apiBaseUrl: string;
  /** Múi giờ của khóa ngày cho trần tin chủ động mỗi ngày. */
  timezone: string;
  maxProactivePerDayPerAccount: number;
  maxSendsPerMinutePerAccount: number;
  blockAfterRejectedSends: number;
  logLevel: string;
};

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

export const MIN_SECRET_LENGTH = 16;

const TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const FALSE_VALUES = new Set(["", "0", "false", "no", "off"]);

type Env = Readonly<Record<string, string | undefined>>;

function readBoolean(env: Env, key: string, fallback: boolean): boolean {
  const raw = env[key]?.trim().toLowerCase();
  if (raw === undefined) return fallback;
  if (TRUE_VALUES.has(raw)) return true;
  if (FALSE_VALUES.has(raw)) return false;
  throw new ConfigError(`${key} must be true or false`);
}

function readPositiveInt(env: Env, key: string, fallback: number): number {
  const raw = env[key]?.trim();
  if (raw === undefined || raw === "") return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1) {
    throw new ConfigError(`${key} must be a positive integer`);
  }
  return value;
}

function readPort(env: Env, key: string, fallback: number): number {
  const value = readPositiveInt(env, key, fallback);
  if (value > 65535) throw new ConfigError(`${key} must be at most 65535`);
  return value;
}

function readString(env: Env, key: string, fallback: string): string {
  const raw = env[key]?.trim();
  return raw === undefined || raw === "" ? fallback : raw;
}

function assertValidTimeZone(timezone: string): void {
  try {
    new Intl.DateTimeFormat("en-CA", { timeZone: timezone });
  } catch {
    throw new ConfigError("PEMA_BOT_TIMEZONE is not a valid IANA time zone");
  }
}

function assertValidUrl(key: string, value: string): void {
  try {
    new URL(value);
  } catch {
    throw new ConfigError(`${key} is not a valid URL`);
  }
}

/** Ném `ConfigError` (không lộ giá trị secret) khi cấu hình sai; boot phải từ chối chạy. */
export function loadConfig(env: Env): BridgeConfig {
  const enabled = readBoolean(env, "PEMA_ZALO_PERSONAL_ENABLED", false);
  const secret = env["PEMA_ZALO_BRIDGE_SECRET"] ?? "";
  if (enabled && secret.length < MIN_SECRET_LENGTH) {
    throw new ConfigError(
      `PEMA_ZALO_BRIDGE_SECRET is required when the bridge is enabled (at least ${MIN_SECRET_LENGTH} characters)`,
    );
  }

  const timezone = readString(env, "PEMA_BOT_TIMEZONE", "Asia/Ho_Chi_Minh");
  assertValidTimeZone(timezone);
  const apiBaseUrl = readString(env, "PEMA_API_BASE_URL", "http://localhost:8000/api/v1").replace(
    /\/+$/,
    "",
  );
  assertValidUrl("PEMA_API_BASE_URL", apiBaseUrl);

  return {
    enabled,
    secret,
    host: readString(env, "PEMA_ZALO_BRIDGE_HOST", "127.0.0.1"),
    port: readPort(env, "PEMA_ZALO_BRIDGE_PORT", 8200),
    apiBaseUrl,
    timezone,
    maxProactivePerDayPerAccount: readPositiveInt(
      env,
      "ZALO_BRIDGE_MAX_PROACTIVE_PER_DAY_PER_ACCOUNT",
      100,
    ),
    maxSendsPerMinutePerAccount: readPositiveInt(
      env,
      "ZALO_BRIDGE_MAX_SENDS_PER_MINUTE_PER_ACCOUNT",
      20,
    ),
    blockAfterRejectedSends: readPositiveInt(env, "ZALO_BRIDGE_BLOCK_AFTER_REJECTED_SENDS", 5),
    logLevel: readString(env, "ZALO_BRIDGE_LOG_LEVEL", "info"),
  };
}
