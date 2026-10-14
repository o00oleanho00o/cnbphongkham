/** Pure helpers of the skills pages: labels, the checks a file must pass, scopes, the list filter. */
import type { Item, Kind, Status } from "./types";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const KINDS: readonly { id: Kind; label: string }[] = [
  { id: "skill", label: "Kỹ năng" },
  { id: "rules", label: "Quy tắc" },
  { id: "persona", label: "Giọng điệu" },
];

export const KIND_LABEL: Record<Kind, string> = { skill: "Kỹ năng", rules: "Quy tắc", persona: "Giọng điệu" };

export const STATUSES: readonly { id: Status; label: string }[] = [
  { id: "active", label: "Đang dùng" },
  { id: "draft", label: "Nháp" },
  { id: "archived", label: "Đã cất" },
];

export const STATUS_LABEL: Record<Status, string> = { active: "Đang dùng", draft: "Nháp", archived: "Đã cất" };
export const STATUS_TONE: Record<Status, Tone> = { active: "success", draft: "warning", archived: "neutral" };
export const ORIGIN_LABEL = { admin: "Quản trị", plugin: "Plugin", agent: "Trợ lý soạn" } as const;

export const NAME_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/;
export const MAX_DESCRIPTION = 300;
const MAX_SKILL = 20_000;
const MAX_TEXT = 6_000;

export function bodyLimit(kind: Kind): number {
  return kind === "skill" ? MAX_SKILL : MAX_TEXT;
}

export interface Writing {
  kind: Kind;
  name: string;
  description: string;
  body: string;
}

/** What stops an item from being stored, in the order a person would fix it; the server checks the same and more. */
export function problems(item: Writing): string[] {
  const found: string[] = [];
  if (!NAME_PATTERN.test(item.name)) {
    found.push("Tên gồm 1 đến 64 ký tự a-z, 0-9, dấu chấm, gạch dưới hoặc gạch ngang, bắt đầu bằng chữ hoặc số.");
  }
  const description = item.description.trim();
  if (!description || description.includes("\n")) found.push("Mô tả là một dòng, không để trống.");
  if (description.length > MAX_DESCRIPTION) found.push(`Mô tả dài tối đa ${MAX_DESCRIPTION} ký tự.`);
  if (!item.body.trim()) found.push("Nội dung đang trống.");
  if (item.body.length > bodyLimit(item.kind)) {
    found.push(`Nội dung dài tối đa ${bodyLimit(item.kind)} ký tự.`);
  }
  return found;
}

export const AGENT_SCOPE = "agent";
const SCOPE_WORD: Record<string, string> = { plugin: "Plugin", channel: "Kênh" };

export function scopeOf(kind: "plugin" | "channel", key: string): string {
  return `${kind}:${key.trim()}`;
}

export function scopeLabel(scope: string): string {
  if (scope === AGENT_SCOPE) return "Cả agent";
  const [kind = "", ...rest] = scope.split(":");
  return `${SCOPE_WORD[kind] ?? kind} ${rest.join(":")}`;
}

/** A scope the server accepts: the whole agent, or a plugin or channel named. */
export function validScope(scope: string): boolean {
  return scope === AGENT_SCOPE || /^(plugin|channel):[a-z0-9][a-z0-9_-]{0,63}$/.test(scope);
}

export function scopesSummary(scopes: readonly string[]): string {
  return scopes.length === 0 ? "Cả agent" : scopes.map(scopeLabel).join(", ");
}

const RANK_LABEL = ["Cả agent", "Plugin", "Kênh"] as const;

export function rankLabel(rank: number): string {
  return RANK_LABEL[rank] ?? String(rank);
}

/** Lower case without diacritics, so "tu van" finds "tư vấn". */
export function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Mn}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();
}

export function filterItems(items: readonly Item[], q: string, kind: Kind | "", status: Status | ""): Item[] {
  const needle = fold(q.trim());
  return items.filter(
    (item) =>
      (kind === "" || item.kind === kind) &&
      (status === "" || item.status === status) &&
      (needle === "" || fold(`${item.name} ${item.description}`).includes(needle)),
  );
}

export function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("vi-VN") : "";
}
