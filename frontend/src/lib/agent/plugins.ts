// The agent's plugins as `GET /v1/admin/plugins` lists them, and the pure rules of the Plugins list and detail
// pages: which plugins are shown, the search, the one-line summary of what a plugin adds.

export interface PluginSetting {
  key: string;
  type: "string" | "number" | "integer" | "boolean";
  title: string;
  description: string;
  required: boolean;
  sensitive: boolean;
  default: unknown;
  value: unknown;
  source: "admin" | "profile" | "default" | null;
}

export interface AgentPlugin {
  name: string;
  version: string;
  description: string;
  origin: string;
  enabled: boolean;
  error: string | null;
  tools: string[];
  channels: string[];
  jobs: string[];
  settings: PluginSetting[];
  secrets_unreadable: boolean;
}

export interface PluginListing {
  plugins: AgentPlugin[];
  broken: Record<string, string>;
}

export const PLUGINS_PATH = "/v1/admin/plugins";
export const PLUGINS_HREF = "/admin/agent/plugins";

/** The agent's own dashboard plugin: the clinic web replaces it, so it is not listed or switched here. */
const OWN_DASHBOARD = "web";

export function pluginHref(name: string): string {
  return `${PLUGINS_HREF}/${encodeURIComponent(name)}`;
}

const fold = (text: string): string =>
  text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();

/** The plugins the clinic web offers, filtered by a search on the name and the description (accents ignored). */
export function shownPlugins(plugins: readonly AgentPlugin[], search: string): AgentPlugin[] {
  const query = fold(search.trim());
  return plugins
    .filter((plugin) => plugin.name !== OWN_DASHBOARD)
    .filter(
      (plugin) => query === "" || fold(`${plugin.name} ${plugin.description}`).includes(query),
    );
}

/** "2 kênh · 1 tool" for what the plugin adds to the agent; empty when it adds none of them. */
export function contributionLine(plugin: AgentPlugin): string {
  const parts: [number, string][] = [
    [plugin.tools.length, "tool"],
    [plugin.channels.length, "kênh"],
    [plugin.jobs.length, "việc nền"],
  ];
  return parts
    .filter(([count]) => count > 0)
    .map(([count, word]) => `${count} ${word}`)
    .join(" · ");
}

/** `PluginOrigin` of the agent: shipped with it, in the profile's folder, installed later. */
const ORIGIN_LABEL: Readonly<Record<string, string>> = {
  bundled: "Có sẵn",
  agent: "Của profile",
  installed: "Cài thêm",
};

export function originLabel(origin: string): string {
  return ORIGIN_LABEL[origin] ?? origin;
}
