/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type { Settings, SettingsPatch, TestResult, Usage } from "./types";

const BASE = "/v1/plugins/jev";

export const jev = {
  settings: () => api.get<Settings>(`${BASE}/settings`),
  saveSettings: (body: SettingsPatch) => api.patch<Settings>(`${BASE}/settings`, body),
  test: () => api.post<TestResult>(`${BASE}/test`),
  usage: () => api.get<Usage>(`${BASE}/usage`),
};

export function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Có lỗi, thử lại sau";
}
