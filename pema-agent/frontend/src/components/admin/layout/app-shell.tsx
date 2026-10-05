// ported from: web/src/app.tsx (DashboardShell)
"use client";

// Deviations: react-router `Routes` became the App Router tree (this component is the `(admin)` layout);
// the shell loads `GET /api/v1/me` (user + permissions) instead of `api.overview()`, filters the menu by
// permission, and adds a phone tab bar. The decorative page background of the original is dropped (waves
// belong to identity areas only, never behind tables). Auth redirects: no session -> /login.
//
// Package U0: the frame, sidebar and top bar are the Pema design kit (`src/ui/`, old Clinic Web look);
// this component only loads the session, the menu and the accounts and fills the kit's slots.
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AccountsProvider } from "@/lib/admin/shared/accounts-context";
import type { AccountInfo } from "@/lib/admin/shared/account-info";
import { coCanHoiTruocKhiRoi, xinPhepRoiTrang } from "@/lib/admin/shared/unsaved-changes-guard";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import { currentNavItem, homeFor, visibleSections, type NavItem, type NavSection } from "@/lib/nav";
import {
  SessionProvider,
  useSession,
  type Permission,
  type UserSummary,
} from "@/lib/session/session-context";
import { AppShell as ShellLayout } from "@/ui/app-shell";
import { Sidebar } from "@/ui/sidebar";
import { TopBar } from "@/ui/top-bar";

import { MobileTabBar } from "./mobile-tab-bar";

type Me = { user: UserSummary; permissions: Permission[] };

/**
 * Khung chính sau đăng nhập. Không có "account đang chọn" toàn cục - các trang
 * dữ liệu mặc định xem trộn mọi account, lọc bằng dropdown ngay trong trang
 * (theo pattern GoClaw); sidebar chỉ còn điều hướng.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<Me | null>(null);
  const [loadError, setLoadError] = useState("");
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    unwrap(http.GET("/api/v1/me"))
      .then((data) => {
        if (!cancelled) setMe({ user: data.user, permissions: data.permissions });
      })
      .catch((e: unknown) => {
        // 401 is already redirecting to /login inside `unwrap`
        if (!cancelled && !(e instanceof ApiError && e.status === 401))
          setLoadError(errorMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const canAccounts = me?.permissions.includes("admin.accounts") ?? false;
  const loadAccounts = useCallback(() => {
    if (!canAccounts) return;
    unwrap(http.GET("/api/v1/admin/accounts"))
      .then((items) =>
        setAccounts(
          items.map((a) => ({
            id: a.id,
            label: a.label,
            enabled: a.enabled ?? true,
            online: !!a.running,
            channel: a.channel,
            policy_profile: a.policy_profile,
          })),
        ),
      )
      .catch(() => setAccounts([]));
  }, [canAccounts]);

  useEffect(() => {
    // Subscribing to server data: the set-state happens in the async callback, not synchronously.
    loadAccounts();
  }, [loadAccounts]);

  // Đóng drawer khi đổi trang (điều hướng bằng tab bar hoặc link trong trang)
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  const permissions = useMemo(() => me?.permissions ?? [], [me]);
  const allows = useCallback(
    (needs: readonly Permission[]) => needs.some((p) => permissions.includes(p)),
    [permissions],
  );
  const sections = useMemo(() => visibleSections(allows), [allows]);

  // `/` redirects to `/today`, the CSKH queue. A role without it (the accountant) goes to its own home instead
  // of a "no permission" card; every other path keeps the card.
  useEffect(() => {
    if (!me || pathname !== "/today" || allows(["crm.task.read"])) return;
    const home = homeFor(allows);
    if (home !== "/login" && home !== "/today") router.replace(home);
  }, [me, pathname, allows, router]);
  const tabs = useMemo<NavItem[]>(
    () => sections.flatMap((s) => s.items).filter((i) => i.tab && !i.planned),
    [sections],
  );
  const accountsValue = useMemo(
    () => ({ accounts, reload: loadAccounts }),
    [accounts, loadAccounts],
  );

  const onLoggedOut = useCallback(() => router.replace("/login"), [router]);

  /** Đăng xuất cũng là RỜI TRANG - phải qua chốt "chưa lưu" như mọi đường rời trang khác. */
  const guardedLogout = useCallback(async (logout: () => Promise<void>) => {
    if (coCanHoiTruocKhiRoi() && !(await xinPhepRoiTrang())) return;
    await logout();
  }, []);

  if (loadError) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-canvas p-6">
        <div className="gc-card max-w-sm p-6 text-center">
          <p className="text-body-lg font-semibold text-ink">Không tải được phiên làm việc</p>
          <p className="mt-1 text-small text-ink-soft">{loadError}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-control bg-brand-500 px-4 py-2 text-body font-medium text-white hover:bg-brand-600"
          >
            Thử lại
          </button>
        </div>
      </div>
    );
  }
  if (!me) {
    return (
      <div
        className="flex min-h-[100dvh] items-center justify-center bg-canvas"
        role="status"
        aria-label="Đang tải"
      >
        <span className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500" />
      </div>
    );
  }

  const current = currentNavItem(pathname);
  const forbidden = current !== undefined && !current.planned && !allows(current.needs);

  return (
    <SessionProvider user={me.user} permissions={me.permissions} onLoggedOut={onLoggedOut}>
      <AccountsProvider value={accountsValue}>
        <ShellFrame
          sections={sections}
          tabs={tabs}
          online={canAccounts ? accounts.some((a) => a.online) : null}
          user={me.user}
          pathname={pathname}
          searchHref={allows(["patient.read"]) ? "/patients" : undefined}
          bellHref={allows(["conversation.read"]) ? "/inbox" : undefined}
          menuOpen={menuOpen}
          onMenu={setMenuOpen}
          onLogoutRequest={guardedLogout}
          forbidden={forbidden}
        >
          {children}
        </ShellFrame>
      </AccountsProvider>
    </SessionProvider>
  );
}

function ShellFrame({
  sections,
  tabs,
  online,
  user,
  pathname,
  searchHref,
  bellHref,
  menuOpen,
  onMenu,
  onLogoutRequest,
  forbidden,
  children,
}: {
  sections: NavSection[];
  tabs: NavItem[];
  online: boolean | null;
  user: UserSummary;
  pathname: string;
  searchHref?: string;
  bellHref?: string;
  menuOpen: boolean;
  onMenu: (open: boolean) => void;
  onLogoutRequest: (logout: () => Promise<void>) => Promise<void>;
  forbidden: boolean;
  children: ReactNode;
}) {
  const { logout } = useSession();
  const closeMenu = useCallback(() => onMenu(false), [onMenu]);
  const openMenu = useCallback(() => onMenu(true), [onMenu]);
  const doLogout = useCallback(() => void onLogoutRequest(logout), [onLogoutRequest, logout]);

  return (
    <ShellLayout
      sidebar={
        <Sidebar
          sections={sections}
          pathname={pathname}
          online={online}
          user={user}
          onLogout={doLogout}
          mobileOpen={menuOpen}
          onCloseMobile={closeMenu}
        />
      }
      topBar={
        <TopBar
          title={currentNavItem(pathname)?.label ?? ""}
          clinicName={user.clinic_name}
          onOpenMenu={openMenu}
          searchHref={searchHref}
          bellHref={bellHref}
        />
      }
      tabBar={<MobileTabBar tabs={tabs} onOpenMenu={openMenu} />}
    >
      {forbidden ? (
        <div className="gc-card mx-auto max-w-md p-6 text-center">
          <p className="text-body-lg font-semibold text-ink">Bạn không có quyền xem màn này</p>
          <p className="mt-1 text-small text-ink-soft">
            Vai trò hiện tại không được cấp quyền. Liên hệ chủ phòng khám hoặc quản lý nếu cần.
          </p>
        </div>
      ) : (
        children
      )}
    </ShellLayout>
  );
}
