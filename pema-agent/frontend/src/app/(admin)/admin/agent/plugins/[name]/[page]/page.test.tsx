// @vitest-environment jsdom
// One page an agent plugin ships, under the plugin's own page: the section's tabs, the plugin's tabs and the page its
// script registered, and every other state (loading, page or plugin not found, script failed, list failed, 403 with
// the API's sentence, 401 to sign-in). The browser is faked: `fetch` answers the listings, `document.head.append`
// "runs" the script.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const nav = vi.hoisted(() => ({
  params: { name: "zalo", page: "accounts" },
  pathname: "/admin/agent/plugins/zalo/accounts",
}));
const signIn = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useParams: () => nav.params,
  usePathname: () => nav.pathname,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/api/client", async (original) => ({
  ...(await original<typeof import("@/lib/api/client")>()),
  redirectToLogin: signIn,
}));

const ZALO = { name: "zalo", script: "/ui/zalo/client.js", styles: [] };

const zaloPlugin = (enabled: boolean) => ({
  name: "zalo",
  version: "0.1.0",
  description: "Kênh Zalo",
  origin: "bundled",
  enabled,
  error: null,
  tools: [],
  channels: [],
  jobs: [],
  settings: [],
  secrets_unreadable: false,
});

function AccountsPage() {
  return <h1>Tài khoản Zalo</h1>;
}

function ContactsPage() {
  return <h1>Danh bạ Zalo</h1>;
}

/** The Zalo script as the browser would run it. */
function runZalo() {
  window.__PEMA_AGENT__?.register("zalo", {
    pages: [
      { id: "accounts", title: "Tài khoản Zalo", component: AccountsPage },
      { id: "contacts", title: "Danh bạ Zalo", component: ContactsPage },
    ],
  });
}

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

function fakeBrowser({
  listing,
  plugins = () => json(200, { plugins: [zaloPlugin(true)], broken: {} }),
  scripts = { "/agent/ui/zalo/client.js": runZalo },
}: {
  listing: () => Promise<Response>;
  plugins?: () => Promise<Response>;
  scripts?: Record<string, () => void>;
}) {
  const fetcher = vi.fn((url: RequestInfo | URL) => {
    if (String(url) === "/agent/v1/admin/ui") return listing();
    if (String(url) === "/agent/v1/admin/plugins") return plugins();
    return Promise.resolve(new Response(null, { status: 404 }));
  });
  vi.stubGlobal("fetch", fetcher);
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
  return fetcher;
}

const uiListing = () => json(200, { home: "/ui/web/", plugins: [ZALO] });

let Layout: ComponentType<{ children: ReactNode }>;
let Page: ComponentType;

async function renderPage(name: string, page: string) {
  nav.params = { name, page };
  nav.pathname = `/admin/agent/plugins/${name}/${page}`;
  vi.resetModules();
  Layout = (await import("../../../layout")).default;
  Page = (await import("./page")).default;
  return render(
    <Layout>
      <Page />
    </Layout>,
  );
}

const linksOf = (navigation: string) =>
  within(screen.getByRole("navigation", { name: navigation })).getAllByRole("link");

beforeEach(() => {
  signIn.mockReset();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete window.__PEMA_AGENT__;
});

describe("a registered page", () => {
  it("draws_the_plugins_component_under_the_tabs_of_the_plugin", async () => {
    fakeBrowser({ listing: uiListing });

    await renderPage("zalo", "contacts");

    expect(await screen.findByRole("heading", { name: "Danh bạ Zalo" })).toBeTruthy();
    const links = linksOf("Trang của plugin zalo");
    expect(links.map((a) => a.textContent)).toEqual([
      "Tổng quan",
      "Tài khoản Zalo",
      "Danh bạ Zalo",
    ]);
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/admin/agent/plugins/zalo",
      "/admin/agent/plugins/zalo/accounts",
      "/admin/agent/plugins/zalo/contacts",
    ]);
    expect(links.map((a) => a.getAttribute("aria-current"))).toEqual([null, null, "page"]);
  });

  it("keeps_only_the_agents_own_pages_in_the_section_tabs", async () => {
    fakeBrowser({ listing: uiListing });

    await renderPage("zalo", "accounts");

    await screen.findByRole("heading", { name: "Tài khoản Zalo" });
    const links = linksOf("Trang quản trị agent");
    expect(links.map((a) => a.textContent)).toEqual(["Tổng quan", "Model", "Plugins"]);
    expect(links[2]?.getAttribute("aria-current")).toBe("page");
  });

  it("gives_the_plugin_the_sdk_before_its_script_runs", async () => {
    fakeBrowser({ listing: uiListing });

    await renderPage("zalo", "accounts");

    await screen.findByRole("heading", { name: "Tài khoản Zalo" });
    expect(window.__PEMA_AGENT__?.version).toBe(1);
  });
});

describe("while loading and when nothing matches", () => {
  it("shows_a_spinner_while_the_listing_loads", async () => {
    fakeBrowser({ listing: () => new Promise<Response>(() => undefined) });

    await renderPage("zalo", "accounts");

    expect(await screen.findByRole("status", { name: "Đang tải trang plugin" })).toBeTruthy();
  });

  it("says_the_plugin_has_no_such_page_and_links_back", async () => {
    fakeBrowser({ listing: uiListing });

    await renderPage("zalo", "khong-co");

    expect(await screen.findByText("Không tìm thấy trang này")).toBeTruthy();
    expect(screen.getByText('Plugin zalo không có trang "khong-co".')).toBeTruthy();
    expect(screen.getByRole("link", { name: "Về trang plugin zalo" }).getAttribute("href")).toBe(
      "/admin/agent/plugins/zalo",
    );
  });

  it("says_a_plugin_that_is_off_has_no_page", async () => {
    fakeBrowser({
      listing: () => json(200, { home: "/ui/web/", plugins: [] }),
      plugins: () => json(200, { plugins: [zaloPlugin(false)], broken: {} }),
    });

    await renderPage("zalo", "accounts");

    expect(
      await screen.findByText("Plugin zalo chưa bật hoặc không có trang quản trị."),
    ).toBeTruthy();
    expect(linksOf("Trang của plugin zalo").map((a) => a.textContent)).toEqual(["Tổng quan"]);
  });
});

describe("failures", () => {
  it("offers_a_retry_when_the_plugins_script_failed_and_draws_the_page_once_it_loads", async () => {
    const scripts: Record<string, () => void> = {};
    fakeBrowser({ listing: uiListing, scripts });

    await renderPage("zalo", "accounts");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Không tải được trang của plugin zalo.");
    scripts["/agent/ui/zalo/client.js"] = runZalo;
    await userEvent.click(within(alert).getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByRole("heading", { name: "Tài khoản Zalo" })).toBeTruthy();
  });

  it("offers_a_retry_when_the_listing_failed", async () => {
    let answer = () => json(502, { error: { message: "Không kết nối được dịch vụ agent." } });
    fakeBrowser({ listing: () => answer() });

    await renderPage("zalo", "accounts");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "Không tải được trang plugin: Không kết nối được dịch vụ agent.",
    );
    answer = uiListing;
    await userEvent.click(within(alert).getByRole("button", { name: "Thử lại" }));
    expect(await screen.findByRole("heading", { name: "Tài khoản Zalo" })).toBeTruthy();
  });

  it("shows_the_apis_sentence_on_a_403", async () => {
    const forbidden = () =>
      json(403, { error: { code: "forbidden", message: "Bạn không có quyền quản trị agent." } });
    fakeBrowser({ listing: forbidden, plugins: forbidden });

    await renderPage("zalo", "accounts");

    expect(await screen.findByText("Bạn không có quyền quản trị agent.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Thử lại" })).toBeNull();
    expect(signIn).not.toHaveBeenCalled();
  });

  it("sends_the_user_to_sign_in_on_a_401", async () => {
    const unauthorized = () =>
      json(401, { error: { code: "unauthorized", message: "Bạn cần đăng nhập." } });
    fakeBrowser({ listing: unauthorized, plugins: unauthorized });

    await renderPage("zalo", "accounts");

    expect(
      await screen.findByText("Phiên đăng nhập đã hết. Đang chuyển tới trang đăng nhập…"),
    ).toBeTruthy();
    expect(signIn).toHaveBeenCalled();
  });
});
