/** Pure helpers of the conversations pages: labels, the retention choices, the staff list. */
import type { ChannelSetting, Conversation, Role, ScenarioScope, ScenarioSettings, Settings } from "./types";

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const ROLE_LABEL: Record<Role, string> = { customer: "Khách", staff: "Nhân viên", agent: "Trợ lý AI" };
export const ROLE_TONE: Record<Role, Tone> = { customer: "neutral", staff: "success", agent: "info" };

export const RETENTION_OPTIONS = [
  { value: "0", label: "Giữ mãi" },
  { value: "30", label: "30 ngày" },
  { value: "90", label: "90 ngày" },
  { value: "180", label: "180 ngày" },
  { value: "365", label: "1 năm" },
] as const;

export const DEFAULT_SCENARIOS: ScenarioSettings = { enabled: true, scope: "plugin", results: 3, min_similarity: 0.55 };
export const NO_SETTINGS: Settings = { channels: {}, retention_days: 0, scenarios: DEFAULT_SCENARIOS };
export const OFF: ChannelSetting = { enabled: false, staff: [], use_scenarios: true };

export const SCOPE_OPTIONS: readonly { value: ScenarioScope; label: string }[] = [
  { value: "plugin", label: "Mọi kênh cùng nền tảng (ví dụ mọi tài khoản Zalo)" },
  { value: "channel", label: "Chỉ kênh đang trả lời" },
  { value: "agent", label: "Cả agent" },
];

export const SIMILARITY_OPTIONS = [
  { value: "0.7", label: "Chặt: chỉ khi rất giống" },
  { value: "0.55", label: "Vừa" },
  { value: "0.4", label: "Rộng: cả khi hơi giống" },
] as const;

export const RESULT_OPTIONS = ["1", "2", "3", "4", "5"].map((value) => ({ value, label: `${value} kịch bản` }));

export function asScope(value: string): ScenarioScope {
  return SCOPE_OPTIONS.find((option) => option.value === value)?.value ?? "plugin";
}

/** The option nearest the stored similarity, so an unusual stored value still shows something. */
export function similarityValue(similarity: number): string {
  const nearest = SIMILARITY_OPTIONS.toSorted(
    (a, b) => Math.abs(Number(a.value) - similarity) - Math.abs(Number(b.value) - similarity),
  )[0];
  return nearest ? nearest.value : "0.55";
}

export function channelSetting(settings: Settings, channel: string): ChannelSetting {
  return settings.channels[channel] ?? OFF;
}

export function withChannel(settings: Settings, channel: string, next: ChannelSetting): Settings {
  return { ...settings, channels: { ...settings.channels, [channel]: next } };
}

export function toggled(ids: readonly string[], id: string, on: boolean): string[] {
  const rest = ids.filter((other) => other !== id);
  return on ? [...rest, id] : rest;
}

/** Every channel the agent runs and every one the settings already mention, each once, in name order. */
export function channelsToShow(known: readonly string[], settings: Settings): string[] {
  return [...new Set([...known, ...Object.keys(settings.channels)])].toSorted();
}

export function retentionValue(days: number): string {
  const found = RETENTION_OPTIONS.find((option) => option.value === String(days));
  return found ? found.value : "0";
}

function normalised(settings: Settings) {
  const channels = Object.entries(settings.channels)
    .filter(([, setting]) => setting.enabled || setting.staff.length > 0 || !setting.use_scenarios)
    .map(([name, setting]) => [name, setting.enabled, setting.staff.toSorted(), setting.use_scenarios] as const)
    .toSorted(([a], [b]) => a.localeCompare(b));
  return { channels, retention_days: settings.retention_days, scenarios: settings.scenarios };
}

export function sameSettings(a: Settings, b: Settings): boolean {
  return JSON.stringify(normalised(a)) === JSON.stringify(normalised(b));
}

/** The name a conversation is listed under: the customer's name, or what is known of a group. */
export function titleOf(conversation: Conversation): string {
  if (conversation.title) return conversation.title;
  return conversation.is_group ? `Nhóm ${conversation.external_id}` : `Chat ${conversation.external_id}`;
}

export function formatTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("vi-VN") : "";
}
