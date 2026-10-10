// @vitest-environment jsdom
// Plugins của agent: one row per plugin that opens the plugin's own page, a search, and "+ Thêm" that only holds
// the place of installing; the agent's own dashboard plugin is not offered.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PluginsPage } from "./plugins-page";

const plugin = (name: string, enabled: boolean, description: string, channels: string[] = []) => ({
  name,
  version: "0.1.0",
  description,
  origin: "bundled",
  enabled,
  error: null,
  tools: [],
  channels,
  jobs: [],
  settings: [],
  secrets_unreadable: false,
});

/** A fake agent over the browser's fetch (an outside system). */
function fakeAgent() {
  vi.stubGlobal("fetch", (url: string) => {
    const listing = {
      plugins: [
        plugin("web", true, "Trang quản trị riêng"),
        plugin("zalo", true, "Kênh Zalo bot, cá nhân, OA", ["zalo_bot", "zalo_personal"]),
        plugin("calculate", false, "Máy tính cho agent"),
      ],
      broken: {},
    };
    const body = url === "/agent/v1/admin/plugins" ? listing : {};
    return Promise.resolve(new Response(JSON.stringify(body)));
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const rows = () =>
  within(screen.getByRole("list", { name: "Danh sách plugin" })).getAllByRole("link");

describe("the plugins list", () => {
  it("lists_one_row_per_plugin_that_opens_its_page", async () => {
    fakeAgent();
    render(<PluginsPage />);

    const zalo = await screen.findByRole("link", { name: /zalo/ });

    expect(zalo.getAttribute("href")).toBe("/admin/agent/plugins/zalo");
    expect(zalo.textContent).toContain("2 kênh");
    expect(zalo.textContent).toContain("Đang bật");
    expect(rows().map((row) => row.getAttribute("href"))).toEqual([
      "/admin/agent/plugins/zalo",
      "/admin/agent/plugins/calculate",
    ]);
  });

  it("has_no_switch_and_no_settings_in_the_list", async () => {
    fakeAgent();
    render(<PluginsPage />);
    await screen.findByRole("link", { name: /zalo/ });

    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByRole("button", { name: /Cài đặt/ })).toBeNull();
  });

  it("filters_by_name_or_description_ignoring_accents", async () => {
    fakeAgent();
    render(<PluginsPage />);
    await screen.findByRole("link", { name: /zalo/ });

    fireEvent.change(screen.getByRole("searchbox", { name: "Tìm plugin" }), {
      target: { value: "may tinh" },
    });

    expect(rows().map((row) => row.getAttribute("href"))).toEqual([
      "/admin/agent/plugins/calculate",
    ]);
  });

  it("says_so_when_nothing_matches", async () => {
    fakeAgent();
    render(<PluginsPage />);
    await screen.findByRole("link", { name: /zalo/ });

    fireEvent.change(screen.getByRole("searchbox", { name: "Tìm plugin" }), {
      target: { value: "email" },
    });

    expect(screen.getByText("Không có plugin nào khớp.")).toBeTruthy();
  });

  it("does_not_list_the_agents_own_dashboard_plugin", async () => {
    fakeAgent();
    render(<PluginsPage />);
    await screen.findByRole("link", { name: /zalo/ });

    expect(screen.queryByRole("link", { name: /^web/ })).toBeNull();
  });

  it("holds_the_place_of_installing_a_plugin", async () => {
    fakeAgent();
    render(<PluginsPage />);
    await screen.findByRole("link", { name: /zalo/ });

    fireEvent.click(screen.getByRole("button", { name: "+ Thêm" }));

    expect(screen.getByText(/Sắp có: cài thêm plugin/)).toBeTruthy();
  });
});
