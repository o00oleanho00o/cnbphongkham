// The tools the agent has or may have (`/v1/admin/tools`), each with an on/off switch: the groups the Công cụ page
// lists them in and the hint some tools carry.
export const TOOLS_PATH = "/v1/admin/tools";

export interface AgentTool {
  name: string;
  description: string;
  source: "core" | "plugin";
  enabled: boolean;
  /** What the profile says. */
  default: boolean;
  /** An admin changed it by hand. */
  stored: boolean;
}

export interface ToolList {
  tools: AgentTool[];
  version: number;
}

export interface ToolGroup {
  key: AgentTool["source"];
  title: string;
  tools: AgentTool[];
}

const GROUP_TITLES: Record<AgentTool["source"], string> = {
  core: "Công cụ lõi",
  plugin: "Công cụ của plugin",
};

export const TOOL_HINTS: Record<string, string> = {
  memory: "Tắt sẽ tắt cả phần nhớ trong prompt của agent.",
};

export const toolPath = (name: string) => `${TOOLS_PATH}/${encodeURIComponent(name)}`;

export function isToolList(value: unknown): value is ToolList {
  return (
    typeof value === "object" && value !== null && "tools" in value && Array.isArray(value.tools)
  );
}

/** Core tools first, then the plugins'; a group with no tool is left out. */
export function groupTools(tools: readonly AgentTool[]): ToolGroup[] {
  return (["core", "plugin"] as const)
    .map((key) => ({ key, title: GROUP_TITLES[key], tools: tools.filter((t) => t.source === key) }))
    .filter((group) => group.tools.length > 0);
}

/** The list with one tool's switch moved, before the agent has answered. */
export function withEnabled(
  tools: readonly AgentTool[],
  name: string,
  enabled: boolean,
): AgentTool[] {
  return tools.map((tool) => (tool.name === name ? { ...tool, enabled } : tool));
}
