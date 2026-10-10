// @vitest-environment jsdom
// The page of one plugin: its switch, its tabs (Tổng quan and the pages it ships), what it adds, and its settings,
// of which only the fields the person changed go to the agent.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentPluginsProvider } from "@/components/agent/agent-plugins";

import { PluginDetailPage } from "./plugin-detail-page";

vi.mock("next/navigation", () => ({ usePathname: () => "/admin/agent/plugins/calculate" }));

const calculate = (enabled: boolean, precision = 10) => ({
  name: "calculate",
  version: "0.1.0",
  description: "Máy tính cho agent",
  origin: "bundled",
  enabled,
  error: null,
  tools: enabled ? ["calculate"] : [],
  channels: [],
  jobs: [],
  settings: [
    {
      key: "precision",
      type: "integer",
      title: "Số chữ số",
      description: "",
      required: false,
      sensitive: false,
      default: 10,
      value: precision,
      source: "profile",
    },
  ],
  secrets_unreadable: false,
});

type Call = { method: string; url: string; body: unknown };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(enabled: boolean): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    calls.push({ method, url, body });
    const answers: Record<string, unknown> = {
      "GET /agent/v1/admin/plugins": { plugins: [calculate(enabled)], broken: {} },
      "POST /agent/v1/admin/plugins/calculate/enable": calculate(true),
      "PATCH /agent/v1/admin/plugins/calculate/settings": calculate(enabled, 4),
      "GET /agent/v1/admin/ui": { plugins: [] },
    };
    return Promise.resolve(new Response(JSON.stringify(answers[`${method} ${url}`] ?? {})));
  });
  return calls;
}

function renderDetail(name = "calculate") {
  return render(
    <AgentPluginsProvider>
      <PluginDetailPage name={name} />
    </AgentPluginsProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__PEMA_AGENT__;
});

describe("the page of one plugin", () => {
  it("switching_the_plugin_on_lists_the_tool_it_adds", async () => {
    const calls = fakeAgent(false);
    renderDetail();

    fireEvent.click(await screen.findByRole("switch", { name: "Bật plugin calculate" }));

    await waitFor(() => expect(screen.getAllByText("Đang bật")).toHaveLength(1));
    expect(calls).toContainEqual({
      method: "POST",
      url: "/agent/v1/admin/plugins/calculate/enable",
      body: undefined,
    });
    expect(screen.getByText("calculate", { selector: "dd" })).toBeTruthy();
  });

  it("saves_only_the_settings_that_changed", async () => {
    const calls = fakeAgent(true);
    renderDetail();

    fireEvent.change(await screen.findByLabelText(/^Số chữ số/), { target: { value: "4" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu cài đặt" }));

    expect(await screen.findByText(/Đã lưu/)).toBeTruthy();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ settings: { precision: 4 } });
  });

  it("has_an_overview_tab_and_a_way_back_to_the_list", async () => {
    fakeAgent(true);
    renderDetail();

    const tabs = await screen.findByRole("navigation", { name: "Trang của plugin calculate" });

    expect(
      within(tabs)
        .getAllByRole("link")
        .map((a) => a.getAttribute("href")),
    ).toEqual(["/admin/agent/plugins/calculate"]);
    expect(screen.getByRole("link", { name: "‹ Plugins" }).getAttribute("href")).toBe(
      "/admin/agent/plugins",
    );
  });

  it("says_the_agent_has_no_such_plugin", async () => {
    fakeAgent(true);
    renderDetail("email");

    expect(await screen.findByText("Không có plugin này")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Về danh sách plugin" }).getAttribute("href")).toBe(
      "/admin/agent/plugins",
    );
  });
});
