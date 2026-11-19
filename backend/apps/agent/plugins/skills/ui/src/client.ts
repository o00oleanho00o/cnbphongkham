/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type {
  ChatReply,
  Choices,
  Effective,
  Item,
  ItemBody,
  ItemList,
  ItemPatch,
  Kind,
  Saved,
  Status,
  Version,
} from "./types";

const BASE = "/v1/plugins/skills";
const id = encodeURIComponent;

function query(params: Record<string, string | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== "")
    .forEach(([key, value]) => search.set(key, String(value)));
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const skills = {
  items: (params: { kind?: Kind; item_status?: Status } = {}) =>
    api.get<ItemList>(`${BASE}/items${query({ ...params })}`),
  item: (item: string) => api.get<Item>(`${BASE}/items/${id(item)}`),
  create: (body: ItemBody) => api.post<Saved>(`${BASE}/items`, body),
  update: (item: string, body: ItemPatch) => api.patch<Saved>(`${BASE}/items/${id(item)}`, body),
  versions: (item: string) => api.get<{ versions: Version[] }>(`${BASE}/items/${id(item)}/versions`),
  restore: (item: string, version: number) =>
    api.post<Saved>(`${BASE}/items/${id(item)}/restore`, { version }),
  /** One turn of the chat with the agent's model that writes drafts for staff. */
  chat: (conversationId: string, text: string, known: Choices) =>
    api.post<ChatReply>(`${BASE}/author/chat`, {
      conversation_id: conversationId,
      text,
      channels: known.channels,
      plugins: known.plugins,
    }),
  effective: (channel: string) => api.get<Effective>(`${BASE}/effective${query({ channel })}`),
};

/** The chat channels the agent runs and the plugins that are on, for choosing where an item applies. */
export async function choices(): Promise<Choices> {
  const [channels, plugins] = await Promise.all([
    api.get<{ channels: { name: string }[] }>("/v1/admin/channels").catch(() => ({ channels: [] })),
    api.get<{ plugins: { name: string; enabled: boolean }[] }>("/v1/admin/plugins").catch(() => ({ plugins: [] })),
  ]);
  return {
    channels: channels.channels.map((channel) => channel.name),
    plugins: plugins.plugins.filter((plugin) => plugin.enabled).map((plugin) => plugin.name),
  };
}

export function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Có lỗi, thử lại sau";
}
