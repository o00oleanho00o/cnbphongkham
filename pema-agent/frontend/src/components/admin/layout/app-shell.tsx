// ported from: web/src/app.tsx (DashboardShell)
"use client";

// Deviations: react-router `Routes` became the App Router tree (this component is the `(admin)` layout);
// the shell loads `GET /api/v1/me` (user + permissions) instead of `api.overview()`, filters the menu by
// permission, and adds a phone tab bar. The decorative page background of the original is dropped (waves
// belong to identity areas only, never behind tables). Auth redirects: no session -> /login.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AccountsProvider } from "@/lib/admin/shared/accounts-context";
import type { AccountInfo } from "@/lib/admin/shared/account-info";
import { coCanHoiTruocKhiRoi, xinPhepRoiTrang } from "@/lib/admin/shared/unsaved-changes-guard";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import { IconMenu } from "@/components/admin/shared/dashboard-icons";
import {
  NAV_SECTIONS,
  isActivePath,
  visibleSections,
  type NavItem,
  type NavSection,
} from "@/lib/nav";
import {
  SessionProvider,
  useSession,
  type Permission,
  type UserSummary,
} from "@/lib/session/session-context";

import { MobileTabBar } from "./mobile-tab-bar";
import { SidebarNav } from "./sidebar-nav";

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
  const tabs = useMemo<NavItem[]>(
    () => sections.flatMap((s) => s.items).filter((i) => i.tab),
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
          <p className="text-[15px] font-semibold text-ink">Không tải được phiên làm việc</p>
          <p className="mt-1 text-[13px] text-ink-soft">{loadError}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-lg bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-600"
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

  const current = NAV_SECTIONS.flatMap((s) => s.items)
    .filter((i) => isActivePath(pathname, i.to))
    .sort((a, b) => b.to.length - a.to.length)[0];
  const forbidden = current !== undefined && !allows(current.needs);

  return (
    <SessionProvider user={me.user} permissions={me.permissions} onLoggedOut={onLoggedOut}>
      <AccountsProvider value={accountsValue}>
        <ShellFrame
          sections={sections}
          tabs={tabs}
          online={accounts.some((a) => a.online)}
          user={me.user}
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
  menuOpen,
  onMenu,
  onLogoutRequest,
  forbidden,
  children,
}: {
  sections: NavSection[];
  tabs: NavItem[];
  online: boolean;
  user: UserSummary;
  menuOpen: boolean;
  onMenu: (open: boolean) => void;
  onLogoutRequest: (logout: () => Promise<void>) => Promise<void>;
  forbidden: boolean;
  children: ReactNode;
}) {
  const { logout } = useSession();
  const router = useRouter();
  const closeMenu = useCallback(() => onMenu(false), [onMenu]);
  const openMenu = useCallback(() => onMenu(true), [onMenu]);
  const doLogout = useCallback(() => void onLogoutRequest(logout), [onLogoutRequest, logout]);

  return (
    <div className="flex min-h-[100dvh] bg-canvas">
      <SidebarNav
        sections={sections}
        online={online}
        user={user}
        onLogout={doLogout}
        mobileOpen={menuOpen}
        onCloseMobile={closeMenu}
      />

      <div className="flex min-w-0 flex-1 flex-col lg:h-screen lg:overflow-hidden">
        {/* Topbar chỉ ở mobile - desktop đã có sidebar cố định */}
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-surface/90 px-4 py-3 backdrop-blur lg:hidden">
          <button
            onClick={openMenu}
            aria-label="Mở menu"
            className="-ml-1.5 rounded-lg p-2 text-ink-soft hover:bg-tile hover:text-ink"
          >
            <IconMenu size={20} />
          </button>
          <Link
            href="/"
            onClick={(e) => {
              if (!coCanHoiTruocKhiRoi()) return;
              e.preventDefault();
              void xinPhepRoiTrang().then((ok) => ok && router.push("/"));
            }}
            className="flex items-center gap-2"
            title="Về trang chính"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- fixed brand asset */}
            <img src="/pema-logo.png" alt="Pema" width={294} height={156} className="h-7 w-auto" />
            <span className="truncate text-[15px] font-semibold text-ink">CSKH</span>
          </Link>
        </header>

        <main
          id="main"
          className="min-w-0 flex-1 px-4 py-5 pb-24 sm:px-6 lg:overflow-y-auto lg:px-8 lg:py-7 lg:pb-7"
        >
          {forbidden ? (
            <div className="gc-card mx-auto max-w-md p-6 text-center">
              <p className="text-[15px] font-semibold text-ink">Bạn không có quyền xem màn này</p>
              <p className="mt-1 text-[13px] text-ink-soft">
                Vai trò hiện tại không được cấp quyền. Liên hệ chủ phòng khám hoặc quản lý nếu cần.
              </p>
            </div>
          ) : (
            children
          )}
        </main>
      </div>

      <MobileTabBar tabs={tabs} onOpenMenu={openMenu} />
    </div>
  );
}
