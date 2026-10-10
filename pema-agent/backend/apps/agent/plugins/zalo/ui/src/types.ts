/** What the plugin's routes (`/v1/plugins/zalo`) take and give; mirrors `plugins/zalo/models.py`. */

export type ChannelKind = "zalo_bot" | "zalo_personal" | "zalo_oa";
export type AllowlistMode = "all" | "list";

export interface Account {
  id: string;
  label: string;
  channel: ChannelKind;
  enabled: boolean;
  allowlist: { mode: AllowlistMode; user_ids: string[] };
  group_require_mention: boolean;
  respond_to_groups: boolean;
  group_passive_listen: boolean;
  auto_react_enabled: boolean;
  auto_react_icon: string;
  typing_indicator_enabled: boolean;
  disabled_tools: string[];
  auto_accept_friends: boolean;
  auto_accept_friend_delay_minutes: number;
  running: boolean;
  has_credentials: boolean;
  warning: string | null;
}

export type AccountUpdate = Partial<Omit<Account, "id" | "channel" | "running" | "has_credentials" | "warning">>;

export interface OaKeys {
  app_id: string;
  app_secret: string;
  oa_secret_key: string;
  refresh_token: string;
}

export interface ReactionIcon {
  key: string;
  emoji: string;
  label: string;
}

export type QrState = "idle" | "waiting_scan" | "scanned" | "success" | "expired" | "error";

export interface QrStatus {
  state: QrState;
  qr_png_base64: string | null;
  detail: string | null;
}

export interface Bridge {
  installed: boolean;
  /** Ready in the agent's image: nothing to install or remove. */
  bundled: boolean;
  installing: boolean;
  version: string | null;
  running: boolean;
  error: string | null;
  log: string[];
}

export interface Contact {
  account_id: string;
  user_id: string;
  display_name: string;
  first_seen: string;
  last_seen: string;
  message_count: number;
}

export interface Group {
  account_id: string;
  thread_id: string;
  name: string;
}

export interface FriendRequest {
  from_uid: string;
  message: string;
  sender_name: string | null;
  avatar_url: string | null;
  received_at: string;
}

export interface Friend {
  user_id: string;
  display_name: string;
  avatar_url: string | null;
}
