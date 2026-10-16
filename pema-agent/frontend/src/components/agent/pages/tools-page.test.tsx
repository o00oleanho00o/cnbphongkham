// @vitest-environment jsdom
// Công cụ của agent: tools grouped as the agent's own and the plugins', each with a switch that moves at once and goes
// back when the agent refuses, a way back to the default for the ones changed by hand, and a hint on the memory tool.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToolsPage } from "./tools-page";

const tool = (name: string, source: string, enabled: boolean, stored = false, def = true) => ({
  name,
  description: `Mô tả của ${name}`,
  source,
  enabled,
  default: def,
  stored,
});

const LIST = {
  tools: [
    tool("get_datetime", "core", true),
    tool("memory", "core", true),
    tool("kb_search", "plugin", true),
    tool("skill_write", "plugin", false, true),
  ],
  version: 2,
};

const listWith = (changed: ReturnType<typeof tool>) => ({
  tools: LIST.tools.map((t) => (t.name === changed.name ? changed : t)),
  version: 3,
});

type Reply = { status?: number; body: unknown };
type Call = { method: string; url: string; body: unknown };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(listing: unknown = LIST, answers: Record<string, Reply> = {}): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    const method = init?.method ?? "GET";
    calls.push({ method, url, body });
    const reply = answers[`${method} ${url}`] ?? { body: listing };
    return Promise.resolve(
      new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 }),
    );
  });
  return calls;
}

const mutations = (calls: Call[]) => calls.filter((c) => c.method !== "GET");
const TOOLS_URL = "/agent/v1/admin/tools";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the tools of the agent", () => {
  it("groups_the_tools_as_core_and_plugin_with_their_description_and_state", async () => {
    fakeAgent();
    render(<ToolsPage />);

    const core = await screen.findByRole("list", { name: "Công cụ lõi" });
    const plugin = screen.getByRole("list", { name: "Công cụ của plugin" });

    expect(within(core).getAllByRole("listitem")).toHaveLength(2);
    expect(within(plugin).getAllByRole("listitem")).toHaveLength(2);
    expect(within(core).getByText("Mô tả của get_datetime")).toBeTruthy();
    expect(screen.getByText(/áp dụng từ lượt trả lời tiếp theo của agent/)).toBeTruthy();
    expect(screen.getAllByText("Mặc định")).toHaveLength(3);
    expect(screen.getAllByText("Đã chỉnh")).toHaveLength(1);
  });

  it("gives_every_tool_an_accessible_switch_that_reflects_its_state", async () => {
    fakeAgent();
    render(<ToolsPage />);

    const on = await screen.findByRole("switch", { name: "Tắt kb_search" });
    const off = screen.getByRole("switch", { name: "Bật skill_write" });

    expect([on.getAttribute("aria-checked"), off.getAttribute("aria-checked")]).toEqual([
      "true",
      "false",
    ]);
  });

  it("hints_that_switching_memory_off_turns_off_the_memory_in_the_prompt", async () => {
    fakeAgent();
    render(<ToolsPage />);

    await screen.findByRole("list", { name: "Công cụ lõi" });

    expect(screen.getAllByText("Tắt sẽ tắt cả phần nhớ trong prompt của agent.")).toHaveLength(1);
  });

  it("shows_the_empty_state_when_the_agent_has_no_tool", async () => {
    fakeAgent({ tools: [], version: 0 });
    render(<ToolsPage />);

    expect(await screen.findByText(/Agent chưa có công cụ nào/)).toBeTruthy();
  });
});

describe("a switch", () => {
  it("sends_the_new_state_and_shows_the_answer_of_the_agent", async () => {
    const calls = fakeAgent(LIST, {
      [`PUT ${TOOLS_URL}/kb_search`]: { body: listWith(tool("kb_search", "plugin", false, true)) },
    });
    render(<ToolsPage />);

    fireEvent.click(await screen.findByRole("switch", { name: "Tắt kb_search" }));

    expect(await screen.findByRole("switch", { name: "Bật kb_search" })).toBeTruthy();
    expect(mutations(calls)).toEqual([
      { method: "PUT", url: `${TOOLS_URL}/kb_search`, body: { enabled: false } },
    ]);
    expect(screen.getAllByText("Đã chỉnh")).toHaveLength(2);
  });

  it("goes_back_and_shows_an_error_when_the_agent_refuses", async () => {
    fakeAgent(LIST, {
      [`PUT ${TOOLS_URL}/kb_search`]: {
        status: 404,
        body: {
          error: { kind: "unknown_tool", message: "no tool 'kb_search' (is its plugin on?)" },
        },
      },
    });
    render(<ToolsPage />);

    fireEvent.click(await screen.findByRole("switch", { name: "Tắt kb_search" }));

    expect(await screen.findByText("no tool 'kb_search' (is its plugin on?)")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Tắt kb_search" }).getAttribute("aria-checked")).toBe(
      "true",
    );
  });
});

describe("back to the default", () => {
  it("is_offered_only_for_a_tool_changed_by_hand_and_sends_null", async () => {
    const calls = fakeAgent(LIST, {
      [`PUT ${TOOLS_URL}/skill_write`]: { body: listWith(tool("skill_write", "plugin", true)) },
    });
    render(<ToolsPage />);

    expect(await screen.findAllByRole("button", { name: /^Về mặc định/ })).toHaveLength(1);
    expect(screen.getByText("Mặc định: bật")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Về mặc định: skill_write" }));

    await waitFor(() =>
      expect(mutations(calls)).toEqual([
        { method: "PUT", url: `${TOOLS_URL}/skill_write`, body: { enabled: null } },
      ]),
    );
    await waitFor(() => expect(screen.queryByRole("button", { name: /^Về mặc định/ })).toBeNull());
  });
});

describe("loading", () => {
  it("shows_the_error_when_the_tools_cannot_be_read", async () => {
    fakeAgent(LIST, {
      [`GET ${TOOLS_URL}`]: {
        status: 403,
        body: { error: { kind: "forbidden", message: "Không đủ quyền" } },
      },
    });
    render(<ToolsPage />);

    expect(await screen.findByText("Không đủ quyền")).toBeTruthy();
  });
});
