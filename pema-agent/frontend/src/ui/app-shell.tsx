import type { ReactNode } from "react";

/**
 * Frame of every signed-in screen: sidebar | (top bar, scrolling main). Purely presentational; the data
 * (session, menu, accounts) is loaded by `components/admin/layout/app-shell.tsx`, which fills the slots.
 *
 * From `lg` the page itself never scrolls: `main` does, so the sidebar and the top bar stay put. Below `lg`
 * the page scrolls normally and `tabBar` (fixed at the bottom) needs the extra bottom padding.
 */
export function AppShell({
  sidebar,
  topBar,
  tabBar,
  children,
}: {
  sidebar: ReactNode;
  topBar: ReactNode;
  tabBar?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-[100dvh] bg-canvas">
      <a
        href="#main"
        className="fixed top-[-80px] left-4 z-(--z-toast) rounded-lg bg-brand-600 px-5 py-3 text-body text-surface focus:top-3"
      >
        Đến nội dung chính
      </a>
      {sidebar}
      <div className="flex min-w-0 flex-1 flex-col lg:h-screen lg:overflow-hidden">
        {topBar}
        <main
          id="main"
          className="min-w-0 flex-1 px-4 py-5 pb-24 sm:px-6 lg:overflow-y-auto lg:px-(--layout-content-pad-x) lg:py-(--layout-content-pad-y) lg:pb-7"
        >
          {children}
        </main>
      </div>
      {tabBar}
    </div>
  );
}
