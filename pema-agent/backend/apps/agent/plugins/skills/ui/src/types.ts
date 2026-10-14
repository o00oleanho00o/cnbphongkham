/** What the plugin's admin routes send and take (`/v1/plugins/skills`). */
export type Kind = "skill" | "rules" | "persona";
export type Status = "draft" | "active" | "archived";
export type Origin = "admin" | "plugin" | "agent";

export interface Item {
  id: string;
  kind: Kind;
  name: string;
  description: string;
  body: string;
  status: Status;
  origin: Origin;
  /** `agent`, `plugin:<name>` or `channel:<name>`; none means the whole agent. */
  scopes: string[];
  meta: Record<string, unknown>;
  usage: Record<string, unknown>;
  version: number;
  updated_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface ItemList {
  items: Item[];
  total: number;
}

export interface ItemBody {
  kind: Kind;
  name: string;
  description: string;
  body: string;
  status: Status;
  scopes: string[];
}

export interface ItemPatch {
  name?: string;
  description?: string;
  body?: string;
  status?: Status;
  scopes?: string[];
  reason?: string;
}

export interface Saved {
  item: Item;
  warnings: string[];
}

export interface Version {
  version: number;
  snapshot: Pick<Item, "name" | "description" | "body" | "status" | "scopes">;
  changed_by: string;
  reason: string;
  created_at: string;
}

export interface Effective {
  channel: string | null;
  plugin: string | null;
  items: { id: string; kind: Kind; name: string; rank: number; scopes: string[] }[];
  text: string | null;
}

/** One turn of the chat that helps write items: the answer, and the items it saved or changed. */
export interface ChatReply {
  reply: string;
  stop: string;
  items: { item: Item; before_version: number | null }[];
}

/** What the dashboard knows of the agent: the chat channels it runs and the plugins that are on. */
export interface Choices {
  channels: string[];
  plugins: string[];
}
