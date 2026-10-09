// @vitest-environment jsdom
// Plugins của agent: switch one on or off; the agent's own dashboard plugin is not offered.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PluginsPage } from "./plugins-page";

const plugin = (name: string, enabled: boolean) => ({
  name,
  version: "0.1.0",
  description: `Plugin ${name}`,
  origin: "bundled",
  enabled,
  error: null,
  tools: [],
  channels: [],
  jobs: [],
  settings: [],
  secrets_unreadable: false,
});

type Call = { method: string; url: string };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ method, url });
    const listing = { plugins: [plugin("web", true), plugin("zalo", false)], broken: {} };
    const answers: Record<string, unknown> = {
      "/agent/v1/admin/plugins": listing,
      "/agent/v1/admin/plugins/zalo/enable": plugin("zalo", true),
      "/agent/v1/admin/ui": { plugins: [] },
    };
    return Promise.resolve(new Response(JSON.stringify(answers[url] ?? {})));
  });
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the plugins page", () => {
  it("switches_a_plugin_on_with_its_toggle", async () => {
    const calls = fakeAgent();
    render(<PluginsPage />);

    fireEvent.click(await screen.findByRole("switch", { name: "Bật plugin zalo" }));

    await waitFor(() => expect(screen.getAllByText("Đang bật")).toHaveLength(1));
    expect(calls).toContainEqual({ method: "POST", url: "/agent/v1/admin/plugins/zalo/enable" });
  });

  it("does_not_list_the_agents_own_dashboard_plugin", async () => {
    fakeAgent();
    render(<PluginsPage />);

    await screen.findByRole("switch", { name: "Bật plugin zalo" });

    expect(screen.queryByRole("switch", { name: "Bật plugin web" })).toBeNull();
  });
});
