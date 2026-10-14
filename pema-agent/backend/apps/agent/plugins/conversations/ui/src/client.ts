/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type { Conversation, ConversationList, Opened, Person, Settings } from "./types";

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
