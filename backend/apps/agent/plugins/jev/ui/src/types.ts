/** What the plugin's admin routes send and take (`/v1/plugins/jev`). */
export interface Settings {
  model: string;
  /** Input tokens a day; 0 is no limit. */
  daily_token_cap: number;
  /** Whether a key is stored (never the key itself). */
  has_key: boolean;
  usd_per_million_tokens: number;
}

export interface SettingsPatch {
  model?: string;
  daily_token_cap?: number;
  /** Replaces the stored key; an empty string removes it. */
  api_key?: string;
}

export interface Day {
  date: string;
  calls: number;
  tokens: number;
  errors: number;
  usd: number;
}

export interface Usage {
  daily_token_cap: number;
  used_today: number;
  days: Day[];
}

export interface TestResult {
  ok: boolean;
  ms: number | null;
  message: string;
}
