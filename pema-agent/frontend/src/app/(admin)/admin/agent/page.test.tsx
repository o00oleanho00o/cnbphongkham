// @vitest-environment jsdom
// `/admin/agent`: opens the first page the enabled plugins registered, or says none has one (naming scripts that
// failed), and shows the listing's problem (403 sentence) like the page host.
import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const router = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/admin/agent",
  useRouter: () => router,
}));

function fakeBrowser(listing: () => Promise<Response>, scripts: Record<string, () => void>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => listing()),
  );
  vi.spyOn(document.head, "append").mockImplementation((...nodes) => {
    nodes.forEach((node) => {
      if (!(node instanceof HTMLScriptElement)) return;
      const run = scripts[node.getAttribute("src") ?? ""];
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
}

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

const Page = () => <p>Trang mẫu</p>;

function runZalo() {
  window.__PEMA_AGENT__?.register("zalo", {
    pages: [
      { id: "accounts", title: "Tài khoản Zalo", component: Page },
      { id: "contacts", title: "Danh bạ Zalo", component: Page },
    ],
  });
}

async function renderIndex() {
  vi.resetModules();
  const Layout: ComponentType<{ children: ReactNode }> = (await import("./layout")).default;
  const Index: ComponentType = (await import("./page")).default;
  return render(
    <Layout>
      <Index />
    </Layout>,
  );
}

beforeEach(() => router.replace.mockReset());

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete window.__PEMA_AGENT__;
});

describe("the agent plugins index", () => {
  it("opens_the_first_registered_page", async () => {
    fakeBrowser(
      () =>
        json(200, {
          home: "/ui/web/",
          plugins: [{ name: "zalo", script: "/ui/zalo/client.js", styles: [] }],
        }),
      { "/agent/ui/zalo/client.js": runZalo },
    );

    await renderIndex();

    await vi.waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith("/admin/agent/p/zalo/accounts"),
    );
  });

  it("says_no_enabled_plugin_has_a_page", async () => {
    fakeBrowser(() => json(200, { home: "/ui/web/", plugins: [] }), {});

    await renderIndex();

    expect(await screen.findByText("Chưa có plugin nào có trang quản trị")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("names_the_plugins_whose_script_failed", async () => {
    fakeBrowser(
      () =>
        json(200, {
          home: "/ui/web/",
          plugins: [{ name: "zalo", script: "/ui/zalo/client.js", styles: [] }],
        }),
      {},
    );

    await renderIndex();

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Không tải được trang của plugin: zalo.",
    );
    expect(screen.getByText("Chưa có plugin nào có trang quản trị")).toBeTruthy();
  });

  it("shows_the_apis_sentence_on_a_403", async () => {
    fakeBrowser(
      () =>
        json(403, { error: { code: "forbidden", message: "Bạn không có quyền quản trị agent." } }),
      {},
    );

    await renderIndex();

    expect(await screen.findByText("Bạn không có quyền quản trị agent.")).toBeTruthy();
    expect(router.replace).not.toHaveBeenCalled();
  });
});
