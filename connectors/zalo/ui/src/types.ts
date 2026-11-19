/** What the connector's admin routes (`/v1/plugins/zalo`) take and give; mirrors `src/zalo_connector/models.py`. */

export type ChannelKind = "zalo_bot" | "zalo_personal" | "zalo_oa";
export type AllowlistMode = "all" | "list";

export interface Account {
  id: string;
  label: string;
  channel: ChannelKind;
  enabled: boolean;
  /** The people answered in a one-to-one chat. */
  allowlist: { mode: AllowlistMode; user_ids: string[] };
  /** The groups answered in; independent of `allowlist` (anyone in an allowed group may ask). */
  group_allowlist: { mode: AllowlistMode; group_ids: string[] };
  group_require_mention: boolean;
  respond_to_groups: boolean;
  /** The groups whose messages are kept; a group not here is not. */
  listen_group_ids: string[];
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
  /** Ready in the connector's image: nothing to install or remove. */
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

/** An item of the skills plugin (a skill, a set of rules or a persona), as far as one account's page needs it. */
export interface SkillItem {
  id: string;
  kind: "skill" | "rules" | "persona";
  name: string;
  description: string;
  status: "draft" | "active" | "archived";
  /** `agent`, `plugin:<name>` or `channel:<name>`; none means the whole agent. */
  scopes: string[];
}

/** What a question on one channel carries: the items that apply (rank 0 agent, 1 plugin, 2 channel) and their text. */
export interface SkillEffective {
  items: { id: string; kind: SkillItem["kind"]; name: string; rank: number; scopes: string[] }[];
  text: string | null;
}
