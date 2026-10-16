// How the Công cụ page lists the tools: the agent's own first, then the plugins', a group with nothing left out.
import { describe, expect, it } from "vitest";

import { type AgentTool, groupTools, isToolList, toolPath, withEnabled } from "./agent-tools";

const tool = (name: string, source: AgentTool["source"], enabled = true): AgentTool => ({
  name,
  description: `Mô tả ${name}`,
  source,
  enabled,
  default: true,
  stored: false,
});

describe("groupTools", () => {
  it("puts_the_core_tools_first_and_the_plugins_tools_second_in_the_order_given", () => {
    const groups = groupTools([
      tool("kb_search", "plugin"),
      tool("get_datetime", "core"),
      tool("memory", "core"),
      tool("skill_write", "plugin"),
    ]);

    expect(groups.map((group) => [group.title, group.tools.map((t) => t.name)])).toEqual([
      ["Công cụ lõi", ["get_datetime", "memory"]],
      ["Công cụ của plugin", ["kb_search", "skill_write"]],
    ]);
  });

  it("leaves_out_a_group_with_no_tool", () => {
    expect(groupTools([tool("memory", "core")]).map((group) => group.key)).toEqual(["core"]);
    expect(groupTools([])).toEqual([]);
  });
});

describe("withEnabled", () => {
  it("moves_one_switch_and_leaves_the_others", () => {
    const list = [tool("a", "core"), tool("b", "plugin")];

    expect(withEnabled(list, "b", false).map((t) => t.enabled)).toEqual([true, false]);
    expect(list[1]?.enabled).toBe(true);
  });
});

describe("paths and shape", () => {
  it("encodes_the_tool_name_in_its_path", () => {
    expect(toolPath("kb_search")).toBe("/v1/admin/tools/kb_search");
    expect(toolPath("a b")).toBe("/v1/admin/tools/a%20b");
  });

  it("recognises_the_answer_of_the_tools_route", () => {
    expect([isToolList({ tools: [], version: 1 }), isToolList({}), isToolList(null)]).toEqual([
      true,
      false,
      false,
    ]);
  });
});
