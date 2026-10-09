/** The dashboard: sign-in first, then a side menu with the built-in pages and the pages plugins add. */
import { type ComponentType, useEffect, useState, useSyncExternalStore } from "react";

import { setSession, getSession, subscribeSession } from "./lib/session";
import { navigate, useRoute } from "./lib/route";
import { AccountPage } from "./pages/account";
import { ApiKeysPage } from "./pages/api-keys";
import { AuthScreen } from "./pages/auth";
import { ModelPage } from "./pages/model";
import { OverviewPage } from "./pages/overview";
import { PluginsPage } from "./pages/plugins";
import { loadPlugins, useContributions } from "./sdk";
import { Button, Empty, Notice } from "./ui/kit";

interface NavItem {
  path: string;
  label: string;
  page: ComponentType;
}

const BUILT_IN: readonly NavItem[] = [
  { path: "/", label: "Tổng quan", page: OverviewPage },
  { path: "/model", label: "Model", page: ModelPage },
  { path: "/plugins", label: "Plugins", page: PluginsPage },
  { path: "/api-keys", label: "API key", page: ApiKeysPage },
  { path: "/account", label: "Tài khoản", page: AccountPage },
];

export function App() {
  const session = useSyncExternalStore(subscribeSession, getSession);
  return session ? <Shell email={session.email} /> : <AuthScreen />;
}

function Shell({ email }: { email: string }) {
  const route = useRoute();
  const contributions = useContributions();
  const [failed, setFailed] = useState<string[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    loadPlugins()
      .then(setFailed)
      .catch(() => setFailed(["?"]));
  }, []);

  const pluginItems: NavItem[] = [...contributions].flatMap(([plugin, contribution]) =>
    (contribution.pages ?? []).map((page) => ({
      path: `/p/${plugin}/${page.id}`,
      label: page.title,
      page: page.component,
    })),
  );
  const items = [...BUILT_IN, ...pluginItems];
  const current = items.find((item) => item.path === route);
  const Page = current?.page;

  function go(path: string) {
    navigate(path);
    setMenuOpen(false);
  }

  return (
    <div className="min-h-dvh md:grid md:grid-cols-[var(--layout-sidebar-w)_1fr]">
      <aside className="border-b border-line bg-surface md:min-h-dvh md:border-r md:border-b-0">
        <div className="flex items-center justify-between px-4 py-4">
          <span className="text-section font-bold text-heading">Pema Agent</span>
          <Button variant="ghost" className="md:hidden" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
            Menu
          </Button>
        </div>
        <nav className={`${menuOpen ? "block" : "hidden"} px-2 pb-4 md:block`} aria-label="Trang">
          <NavList items={BUILT_IN} route={route} go={go} />
          {pluginItems.length > 0 && (
            <>
              <p className="mt-4 mb-1 px-3 text-micro font-semibold tracking-wider text-ink-soft uppercase">Plugin</p>
              <NavList items={pluginItems} route={route} go={go} />
            </>
          )}
          <div className="mt-6 border-t border-line px-3 pt-4">
            <p className="text-label break-all text-ink-soft">{email}</p>
            <Button variant="ghost" className="mt-1 -ml-4" onClick={() => setSession(null)}>
              Đăng xuất
            </Button>
          </div>
        </nav>
      </aside>
      <main className="mx-auto w-full max-w-6xl p-4 md:p-7">
        {failed.length > 0 && (
          <div className="mb-4">
            <Notice tone="warning">Không tải được trang của plugin: {failed.join(", ")}</Notice>
          </div>
        )}
        {Page ? <Page /> : <Empty>Không có trang này (plugin đã tắt?).</Empty>}
      </main>
    </div>
  );
}

function NavList({ items, route, go }: { items: readonly NavItem[]; route: string; go: (path: string) => void }) {
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const active = item.path === route;
        return (
          <li key={item.path}>
            <button
              type="button"
              aria-current={active ? "page" : undefined}
              onClick={() => go(item.path)}
              className={`flex min-h-11 w-full items-center rounded-control px-3 text-left text-body sm:min-h-9 ${
                active ? "bg-brand-50 font-semibold text-brand-700" : "text-ink hover:bg-tile"
              }`}
            >
              {item.label}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
