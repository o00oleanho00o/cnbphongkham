"use client";

// The sidebar of the old Pema Clinic Web (white, 232px, logo + "PHÒNG KHÁM DA LIỄU", small-caps section
// titles, active item on a pale blue pill) carrying the old sections first and the sections of this app
// after them (see `lib/nav.tsx`). From `lg` it is a fixed column; below `lg` a drawer opened from the top bar.
//
// `lg:h-screen` is required: the outer frame only sets a floor (`min-h-[100dvh]`), so without a ceiling the
// sidebar grows with its content, the whole document scrolls and the logo drifts away. The `<nav>` scrolls
// inside the column instead.
import {
  IconClose,
  IconLogout,
  IconMoon,
  IconSun,
} from "@/components/admin/shared/dashboard-icons";
import { useTheme } from "@/lib/admin/shared/use-theme";
import { isActivePath, type NavSection } from "@/lib/nav";
import { ROLE_LABEL, type UserSummary } from "@/lib/session/session-context";

import { cx } from "./classnames";
import { GuardedLink } from "./guarded-link";

/** Footer text before the version: nothing when the role cannot see the accounts. */
function connectionLabel(online: boolean | null): string {
  if (online === null) return "";
  return online ? "Đã kết nối · " : "Ngoại tuyến · ";
}

const ITEM_BASE =
  "mb-0.5 flex items-center gap-2.5 rounded-xl px-3 py-[11px] text-body transition-colors";

export function Sidebar({
  sections,
  pathname,
  online,
  user,
  onLogout,
  mobileOpen,
  onCloseMobile,
}: {
  sections: NavSection[];
  pathname: string;
  /** At least one Zalo account is running (status dot in the footer); null = the role cannot see accounts. */
  online: boolean | null;
  user: UserSummary;
  onLogout: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const { theme, toggle } = useTheme();

  return (
    <>
      {mobileOpen && (
        <button
          aria-label="Đóng menu"
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[2px] lg:hidden"
        />
      )}

      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-(--z-drawer) flex w-72 flex-col border-r border-line bg-surface transition-transform duration-200 lg:static lg:z-auto lg:h-screen lg:w-(--layout-sidebar-w) lg:shrink-0 lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Điều hướng chính"
      >
        <div className="flex items-start gap-2.5 px-5 pt-6 pb-5">
          <GuardedLink href="/" onNavigate={onCloseMobile} className="block" title="Về trang chính">
            {/* eslint-disable-next-line @next/next/no-img-element -- fixed 294x156 brand asset */}
            <img
              src="/pema-logo.png"
              alt="Pema"
              width={294}
              height={156}
              className="h-auto w-[118px] dark:rounded-tile dark:bg-plate dark:p-1.5"
            />
            <span className="mt-2 block text-eyebrow font-semibold tracking-[0.1em] text-ink-soft">
              PHÒNG KHÁM DA LIỄU
            </span>
          </GuardedLink>
          <button
            onClick={onCloseMobile}
            aria-label="Đóng menu"
            className="ml-auto rounded-lg p-1.5 text-ink-soft hover:bg-tile lg:hidden"
          >
            <IconClose size={17} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3" aria-label="Chức năng">
          {sections.map((section) => (
            <div key={section.title} className="mb-4">
              <div className="px-2.5 pt-1 pb-1.5 text-eyebrow font-semibold tracking-[0.12em] text-ink-soft uppercase">
                {section.title}
              </div>
              {section.items.map((item) => {
                if (item.planned) {
                  return (
                    <span
                      key={item.to}
                      aria-disabled="true"
                      title="Màn này sẽ có ở bản sau"
                      className={cx(ITEM_BASE, "cursor-not-allowed text-ink-soft/60")}
                    >
                      <item.icon size={17} />
                      <span className="min-w-0 flex-1 leading-snug">{item.label}</span>
                      <span className="sr-only">(sắp có)</span>
                    </span>
                  );
                }
                const active = isActivePath(pathname, item.to);
                return (
                  <GuardedLink
                    key={item.to}
                    href={item.to}
                    aria-current={active ? "page" : undefined}
                    onNavigate={onCloseMobile}
                    className={cx(
                      ITEM_BASE,
                      active
                        ? "bg-brand-50 font-semibold text-brand-700"
                        : "text-ink-soft hover:bg-tile hover:text-ink",
                    )}
                  >
                    <item.icon size={17} />
                    <span className="min-w-0 flex-1 leading-snug">{item.label}</span>
                  </GuardedLink>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="border-t border-line px-4 py-3">
          <div className="mb-2 flex items-center gap-2.5">
            <span
              aria-hidden
              className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full border border-brand-100 bg-brand-50 text-label font-bold text-brand-700"
            >
              {(user.display_name.trim()[0] ?? "?").toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className="truncate text-label font-bold text-ink">{user.display_name}</div>
              <div className="truncate text-eyebrow text-ink-soft">
                {ROLE_LABEL[user.role]} · {user.clinic_name}
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-label text-ink-soft">
              {online !== null && (
                <span
                  aria-hidden
                  className={cx("h-2 w-2 rounded-pill", online ? "bg-success" : "bg-line-strong")}
                />
              )}
              {connectionLabel(online)}v{process.env.NEXT_PUBLIC_APP_VERSION}
            </span>
            <div className="flex items-center gap-0.5">
              <button
                onClick={toggle}
                title={
                  theme === "dark"
                    ? "Đang tối - bấm để chuyển sáng"
                    : "Đang sáng - bấm để chuyển tối"
                }
                aria-label="Đổi giao diện sáng/tối"
                className="rounded-lg p-1.5 text-ink-soft hover:bg-tile hover:text-ink"
              >
                {theme === "dark" ? <IconSun size={16} /> : <IconMoon size={16} />}
              </button>
              <button
                onClick={onLogout}
                title="Đăng xuất"
                aria-label="Đăng xuất"
                className="rounded-lg p-1.5 text-ink-soft hover:bg-tile hover:text-ink"
              >
                <IconLogout size={16} />
              </button>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
