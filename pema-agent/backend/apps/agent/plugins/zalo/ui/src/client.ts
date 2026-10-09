/** The plugin's admin routes, signed by the dashboard's session. */
import { api } from "./sdk";
import type {
  Account,
  AccountUpdate,
  Bridge,
  ChannelKind,
  Contact,
  Friend,
  FriendRequest,
  Group,
  OaKeys,
  QrStatus,
  ReactionIcon,
} from "./types";

const BASE = "/v1/plugins/zalo";
const id = encodeURIComponent;

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const zalo = {
  accounts: () => api.get<Account[]>(`${BASE}/accounts`),
  create: (body: { id: string; label: string; channel: ChannelKind }) =>
    api.post<Account>(`${BASE}/accounts`, body),
  update: (account: string, body: AccountUpdate) => api.patch<Account>(`${BASE}/accounts/${id(account)}`, body),
  remove: (account: string) => api.del<void>(`${BASE}/accounts/${id(account)}`),
  setBotToken: (account: string, token: string) =>
    api.put<Account>(`${BASE}/accounts/${id(account)}/bot-token`, { token }),
  setOaKeys: (account: string, keys: OaKeys) => api.put<Account>(`${BASE}/accounts/${id(account)}/oa-keys`, keys),
  reactionIcons: () => api.get<ReactionIcon[]>(`${BASE}/accounts/reaction-icons`),
  startLogin: (account: string) => api.post<QrStatus>(`${BASE}/accounts/${id(account)}/login`),
  loginStatus: (account: string) => api.get<QrStatus>(`${BASE}/accounts/${id(account)}/login/status`),
  bridge: () => api.get<Bridge>(`${BASE}/bridge`),
  installBridge: () => api.post<Bridge>(`${BASE}/bridge/install`),
  uninstallBridge: () => api.del<Bridge>(`${BASE}/bridge`),
  friendRequests: (account: string) => api.get<FriendRequest[]>(`${BASE}/friends/${id(account)}/requests`),
  friends: (account: string) => api.get<Friend[]>(`${BASE}/friends/${id(account)}/list`),
  decide: (account: string, uid: string, accept: boolean) =>
    api.post<void>(`${BASE}/friends/${id(account)}/${accept ? "accept" : "reject"}`, { uid }),
  contacts: (params: { account_id?: string; q?: string; limit: number; offset: number }) =>
    api.get<Contact[]>(`${BASE}/contacts${query(params)}`),
  deleteContact: (account: string, user: string) => api.del<void>(`${BASE}/contacts/${id(account)}/${id(user)}`),
  groups: (account?: string) => api.get<Group[]>(`${BASE}/groups${query({ account_id: account })}`),
};

/** The tools of the enabled plugins, which an account may switch off. */
export async function agentTools(): Promise<string[]> {
  const listing = await api.get<{ plugins: { enabled: boolean; tools: string[] }[] }>("/v1/admin/plugins");
  const names = listing.plugins.filter((p) => p.enabled).flatMap((p) => p.tools);
  return [...new Set(names)].sort();
}

export function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : "Có lỗi, thử lại sau";
}
