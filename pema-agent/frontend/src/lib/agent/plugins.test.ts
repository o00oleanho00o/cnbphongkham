// Pure rules of the Plugins pages: what is listed, the search, the summary of what a plugin adds.
import { describe, expect, it } from "vitest";

import { type AgentPlugin, contributionLine, originLabel, shownPlugins } from "./plugins";

const plugin = (name: string, extra: Partial<AgentPlugin> = {}): AgentPlugin => ({
  name,
  version: "0.1.0",
  description: "",
  origin: "bundled",
  enabled: true,
  error: null,
  tools: [],
  channels: [],
  jobs: [],
  settings: [],
  secrets_unreadable: false,
  ...extra,
});

describe("shownPlugins", () => {
  const all = [
    plugin("web"),
    plugin("zalo", { description: "Kênh Zalo" }),
    plugin("calculate", { description: "Máy tính" }),
  ];

  it("leaves_out_the_agents_own_dashboard", () => {
    expect(shownPlugins(all, "").map((p) => p.name)).toEqual(["zalo", "calculate"]);
  });

  it("matches_the_name_or_the_description_without_accents_or_case", () => {
    expect(shownPlugins(all, "  MAY TINH ").map((p) => p.name)).toEqual(["calculate"]);
    expect(shownPlugins(all, "kenh").map((p) => p.name)).toEqual(["zalo"]);
  });
});

describe("contributionLine", () => {
  it("counts_tools_channels_and_jobs_it_adds", () => {
    expect(contributionLine(plugin("zalo", { channels: ["a", "b"], jobs: ["j"] }))).toBe(
      "2 kênh · 1 việc nền",
    );
  });

  it("is_empty_when_it_adds_none", () => {
    expect(contributionLine(plugin("sso"))).toBe("");
  });
});

describe("originLabel", () => {
  it("words_the_agents_origins_and_keeps_an_unknown_one", () => {
    expect(originLabel("bundled")).toBe("Có sẵn");
    expect(originLabel("installed")).toBe("Cài thêm");
    expect(originLabel("other")).toBe("other");
  });
});
