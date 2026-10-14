/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type {
  Conversation,
  ConversationList,
  Opened,
  Person,
  Scenario,
  ScenarioHit,
  ScenarioList,
  ScenarioStatus,
  Settings,
} from "./types";

const BASE = "/v1/plugins/conversations";
const id = encodeURIComponent;

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== "")
    .forEach(([key, value]) => search.set(key, String(value)));
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const conversations = {
  settings: () => api.get<Settings>(`${BASE}/settings`),
  saveSettings: (settings: Settings) => api.put<Settings>(`${BASE}/settings`, settings),
  list: (params: { channel?: string; q?: string; limit?: number; offset?: number }) =>
    api.get<ConversationList>(`${BASE}/conversations${query(params)}`),
  open: (conversation: string) => api.get<Opened>(`${BASE}/conversations/${id(conversation)}`),
  leaveOut: (conversation: string, excluded: boolean) =>
    api.patch<Conversation>(`${BASE}/conversations/${id(conversation)}`, { excluded }),
  remove: (conversation: string) => api.del<{ deleted: boolean }>(`${BASE}/conversations/${id(conversation)}`),
  people: (channel: string) => api.get<{ people: Person[] }>(`${BASE}/people${query({ channel })}`),
};

export const scenarios = {
  list: (params: { channel?: string; q?: string; limit?: number; offset?: number }) =>
    api.get<ScenarioList>(`${BASE}/scenarios${query(params)}`),
  status: () => api.get<ScenarioStatus>(`${BASE}/scenarios/status`),
  refresh: () => api.post<{ conversations: number; new: number; joined: number }>(`${BASE}/scenarios/refresh`, {}),
  search: (question: string, channel: string) =>
    api.post<{ hits: ScenarioHit[]; scope: string }>(`${BASE}/scenarios/search`, {
      query: question,
      channel: channel === "" ? null : channel,
    }),
  enable: (scenario: string, enabled: boolean) =>
    api.patch<Scenario>(`${BASE}/scenarios/${id(scenario)}`, { enabled }),
  remove: (scenario: string) => api.del<{ deleted: boolean }>(`${BASE}/scenarios/${id(scenario)}`),
};

/** The chat channels the agent runs, for choosing which ones keep their conversations. */
export async function channelNames(): Promise<string[]> {
  const found = await api
    .get<{ channels: { name: string }[] }>("/v1/admin/channels")
    .catch(() => ({ channels: [] as { name: string }[] }));
  return found.channels.map((channel) => channel.name);
}

export function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Có lỗi, thử lại sau";
}
