/** What the plugin's admin routes send and take (`/v1/plugins/conversations`). */
export type Role = "customer" | "staff" | "agent";

export interface Conversation {
  id: string;
  channel: string;
  external_id: string;
  is_group: boolean;
  title: string;
  excluded: boolean;
  message_count: number;
  first_at: string;
  last_at: string;
}

export interface ConversationList {
  conversations: Conversation[];
  total: number;
}

export interface Message {
  seq: number;
  message_id: string;
  sender_id: string;
  sender_name: string;
  role: Role;
  at: string;
  text: string;
  answered: boolean;
}

export interface Opened {
  conversation: Conversation;
  messages: Message[];
}

export interface Person {
  sender_id: string;
  name: string;
  messages: number;
  role: Role;
}

export interface ChannelSetting {
  enabled: boolean;
  /** Ids of the people of the channel who are staff. */
  staff: string[];
}

export interface Settings {
  channels: Record<string, ChannelSetting>;
  /** Messages older than this many days are deleted; 0 keeps them for ever. */
  retention_days: number;
}
