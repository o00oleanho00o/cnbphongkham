// @vitest-environment jsdom
// The plugin SDK host: `window.__PEMA_AGENT__` (this app's React, the agent's `api`, the kit names), the store of
// registered pages, and `loadPlugins` (one listing, scripts and styles under `/agent`, plugins switched off forgotten,
// failed scripts named). jsdom runs no scripts, so `document.head.append` plays the browser: it "runs" a script by
// letting it register, or fails it.
import { act, cleanup, render, screen } from "@testing-library/react";
import * as React from "react";
import * as jsxRuntime from "react/jsx-runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Api } from "./api";

type SdkModule = typeof import("./sdk");

let sdk: SdkModule;

const Page = () => <p>Trang mẫu</p>;

type Listing = { plugins: { name: string; script: string; styles: string[] }[] };

function fakeApi(listing: () => Listing | Promise<Listing>) {
  const get = vi.fn((_path: string) => Promise.resolve(listing()));
  const never = () => Promise.reject(new Error("not used"));
  const api = { request: never, get, post: never, put: never, patch: never, del: never };
  return api as unknown as Api & { get: typeof get };
}

/** Scripts the "browser" runs: src -> what it does; anything else fails to load. */
function browser(scripts: Record<string, () => void>) {
  const appended: string[] = [];
  vi.spyOn(document.head, "append").mockImplementation((...nodes) => {
    nodes.forEach((node) => {
      if (node instanceof HTMLLinkElement) appended.push(`style ${node.getAttribute("href")}`);
      if (!(node instanceof HTMLScriptElement)) return;
      const src = node.getAttribute("src") ?? "";
      appended.push(`script ${src}`);
      const run = scripts[src];
      queueMicrotask(() => {
        if (!run) {
          node.onerror?.(new Event("error"));
          return;
        }
        run();
        node.onload?.(new Event("load"));
      });
    });
  });
  return appended;
}

const zaloScript = () =>
  window.__PEMA_AGENT__?.register("zalo", {
    pages: [{ id: "accounts", title: "Tài khoản Zalo", component: Page }],
  });

beforeEach(async () => {
  vi.resetModules();
  sdk = await import("./sdk");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.__PEMA_AGENT__;
});

describe("installAgentSdk", () => {
  it("hands_plugins_this_apps_react_the_api_the_kit_and_register", () => {
    const api = fakeApi(() => ({ plugins: [] }));

    sdk.installAgentSdk(api);

    const host = window.__PEMA_AGENT__;
    expect(host?.version).toBe(1);
    expect(host?.React.useState).toBe(React.useState);
    expect(host?.jsxRuntime.jsx).toBe(jsxRuntime.jsx);
    expect(host?.api).toBe(api);
    expect(Object.keys(host?.ui ?? {}).sort()).toEqual(
      [
        "Badge",
        "Button",
        "Card",
        "Empty",
        "FIELD_CLASS",
        "Field",
        "Input",
        "Notice",
        "PageHeader",
        "Select",
        "Toggle",
      ].sort(),
    );
    host?.register("zalo", { pages: [] });
    expect(sdk.contributions().has("zalo")).toBe(true);
  });
});

describe("the store of registered pages", () => {
  function Titles() {
    const registered = sdk.useContributions();
    const titles = [...registered.values()].flatMap((c) => (c.pages ?? []).map((p) => p.title));
    return <p data-testid="titles">{titles.join(",")}</p>;
  }

  it("redraws_on_register_and_on_forget", () => {
    render(<Titles />);
    expect(screen.getByTestId("titles").textContent).toBe("");

    act(() => sdk.register("zalo", { pages: [{ id: "a", title: "A", component: Page }] }));
    expect(screen.getByTestId("titles").textContent).toBe("A");

    act(() => sdk.register("zalo", { pages: [{ id: "b", title: "B", component: Page }] }));
    expect(screen.getByTestId("titles").textContent).toBe("B");

    act(() => sdk.forget("zalo"));
    expect(screen.getByTestId("titles").textContent).toBe("");
  });

  it("gives_a_new_map_each_change_and_keeps_the_old_one_intact", () => {
    sdk.register("zalo", { pages: [] });
    const before = sdk.contributions();

    sdk.register("lich", { pages: [] });

    expect(sdk.contributions()).not.toBe(before);
    expect([...before.keys()]).toEqual(["zalo"]);
    expect([...sdk.contributions().keys()]).toEqual(["zalo", "lich"]);
  });

  it("ignores_forgetting_a_plugin_it_never_had", () => {
    const before = sdk.contributions();

    sdk.forget("khong-co");

    expect(sdk.contributions()).toBe(before);
  });
});

describe("loadPlugins", () => {
  it("reads_the_listing_and_loads_each_script_and_style_under_agent", async () => {
    const appended = browser({ "/agent/ui/zalo/client.js": zaloScript });
    const api = fakeApi(() => ({
      plugins: [{ name: "zalo", script: "/ui/zalo/client.js", styles: ["/ui/zalo/client.css"] }],
    }));
    sdk.installAgentSdk(api);

    const failed = await sdk.loadPlugins(api);

    expect(api.get).toHaveBeenCalledWith("/v1/admin/ui");
    expect(failed).toEqual([]);
    expect(appended).toEqual([
      "style /agent/ui/zalo/client.css",
      "script /agent/ui/zalo/client.js",
    ]);
    expect(sdk.contributions().get("zalo")?.pages?.[0]?.id).toBe("accounts");
  });

  it("does_not_load_a_script_twice", async () => {
    const appended = browser({ "/agent/ui/zalo/client.js": zaloScript });
    const api = fakeApi(() => ({
      plugins: [{ name: "zalo", script: "/ui/zalo/client.js", styles: [] }],
    }));
    sdk.installAgentSdk(api);

    await sdk.loadPlugins(api);
    await sdk.loadPlugins(api);

    expect(appended).toEqual(["script /agent/ui/zalo/client.js"]);
  });

  it("shares_one_run_between_calls_made_meanwhile", async () => {
    browser({ "/agent/ui/zalo/client.js": zaloScript });
    const api = fakeApi(() => ({
      plugins: [{ name: "zalo", script: "/ui/zalo/client.js", styles: [] }],
    }));
    sdk.installAgentSdk(api);

    await Promise.all([sdk.loadPlugins(api), sdk.loadPlugins(api)]);

    expect(api.get).toHaveBeenCalledOnce();
  });

  it("forgets_a_plugin_switched_off_and_loads_it_again_when_it_comes_back", async () => {
    const appended = browser({ "/agent/ui/zalo/client.js": zaloScript });
    const zalo = { name: "zalo", script: "/ui/zalo/client.js", styles: [] };
    let enabled = true;
    const api = fakeApi(() => ({ plugins: enabled ? [zalo] : [] }));
    sdk.installAgentSdk(api);

    await sdk.loadPlugins(api);
    enabled = false;
    await sdk.loadPlugins(api);
    expect(sdk.contributions().has("zalo")).toBe(false);

    enabled = true;
    await sdk.loadPlugins(api);
    expect(sdk.contributions().has("zalo")).toBe(true);
    expect(appended).toEqual([
      "script /agent/ui/zalo/client.js",
      "script /agent/ui/zalo/client.js",
    ]);
  });

  it("names_the_plugins_whose_script_failed_and_keeps_the_others", async () => {
    browser({ "/agent/ui/zalo/client.js": zaloScript });
    const api = fakeApi(() => ({
      plugins: [
        { name: "zalo", script: "/ui/zalo/client.js", styles: [] },
        { name: "hong", script: "/ui/hong/client.js", styles: [] },
      ],
    }));
    sdk.installAgentSdk(api);

    const failed = await sdk.loadPlugins(api);

    expect(failed).toEqual(["hong"]);
    expect([...sdk.contributions().keys()]).toEqual(["zalo"]);
  });

  it("rejects_when_the_listing_cannot_be_read", async () => {
    const api = fakeApi(() => Promise.reject(new Error("Bạn không có quyền quản trị agent.")));

    await expect(sdk.loadPlugins(api)).rejects.toThrow("Bạn không có quyền quản trị agent.");
  });
});
