/** Pure rules of the Jev page: the numbers as people write them, what a form sends, the words about the day. */
import type { Settings, SettingsPatch } from "./types";

export const MAX_TOKENS = 10_000_000_000;
export const MODEL_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/;
const MIN_KEY = 8;
const MAX_KEY = 500;

/** 2000000 as "2.000.000". */
export const formatCount = (count: number): string => String(count).replace(/\B(?=(\d{3})+(?!\d))/g, ".");

/** The tokens typed ("2.000.000", "2 000 000", "2000000"); null when it is not a whole number in range. */
export function parseTokens(text: string): number | null {
  const digits = text.trim().replace(/[.,\s]/g, "");
  if (!/^\d+$/.test(digits)) return null;
  const count = Number(digits);
  return count <= MAX_TOKENS ? count : null;
}

/** "$0,000084": the price of these tokens, with as many decimals as a small sum needs. */
export function formatUsd(usd: number): string {
  const digits = usd < 0.01 ? 6 : 4;
  return `$${usd.toFixed(digits).replace(".", ",")}`;
}

export const usdOf = (tokens: number, perMillion: number): number => (tokens * perMillion) / 1_000_000;

export interface Form {
  model: string;
  /** Typed text, read by `parseTokens`. */
  cap: string;
}

export const formOf = (saved: Settings): Form => ({ model: saved.model, cap: formatCount(saved.daily_token_cap) });

export interface Problems {
  model?: string;
  cap?: string;
  key?: string;
}

export function problems(form: Form, key: string): Problems {
  return {
    model: MODEL_PATTERN.test(form.model.trim())
      ? undefined
      : "Tên model gồm chữ thường, số, dấu chấm, gạch dưới hoặc gạch ngang.",
    cap: parseTokens(form.cap) === null ? "Nhập một số nguyên từ 0 đến 10.000.000.000." : undefined,
    key: keyProblem(key),
  };
}

function keyProblem(key: string): string | undefined {
  const length = key.trim().length;
  const fine = length === 0 || (length >= MIN_KEY && length <= MAX_KEY);
  return fine ? undefined : `Khóa dài từ ${MIN_KEY} đến ${MAX_KEY} ký tự.`;
}

export const hasProblems = (found: Problems): boolean => Object.values(found).some((text) => text !== undefined);

/** What to send for the settings (model and allowance), or null when neither changed. */
export function settingsChange(form: Form, saved: Settings): SettingsPatch | null {
  const model = form.model.trim();
  const cap = parseTokens(form.cap);
  const patch: SettingsPatch = {
    ...(model !== saved.model ? { model } : {}),
    ...(cap !== null && cap !== saved.daily_token_cap ? { daily_token_cap: cap } : {}),
  };
  return Object.keys(patch).length === 0 ? null : patch;
}

/** "Hôm nay 120.000 / 2.000.000 token (6%)", or without the limit when there is none. */
export function todayText(used: number, cap: number): string {
  if (cap === 0) return `Hôm nay ${formatCount(used)} token (không giới hạn)`;
  const share = Math.min(100, Math.round((used / cap) * 100));
  return `Hôm nay ${formatCount(used)} / ${formatCount(cap)} token (${share}%)`;
}

/** The sentence under the allowance field: what using all of it would cost. */
export function capHint(cap: number | null, perMillion: number): string {
  if (cap === null) return "Số token đầu vào tối đa mỗi ngày; 0 là không giới hạn.";
  if (cap === 0) return "Không giới hạn: chi phí chỉ tùy số lần tìm.";
  return `Dùng hết hạn mức thì khoảng ${formatUsd(usdOf(cap, perMillion))} mỗi ngày.`;
}
