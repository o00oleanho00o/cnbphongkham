// ported from: web/src/layout/sidebar-nav.tsx
"use client";

// Deviations: react-router `NavLink`/`useNavigate` became `next/link` + `usePathname`/`useRouter`; the
// menu is data (`lib/nav.tsx`) filtered by the BE's permissions; the Zalo logo is the Pema logo; the
// footer also shows who is signed in. The "new version on GitHub" button is gone: the BE has no version
// feed and a self-hosted clinic updates through infra, not from this page.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { MouseEvent } from "react";

import {
  IconClose,
  IconLogout,
  IconMoon,
  IconSun,
} from "@/components/admin/shared/dashboard-icons";
import { isActivePath, type NavSection } from "@/lib/nav";
import { ROLE_LABEL, type UserSummary } from "@/lib/session/session-context";
import { coCanHoiTruocKhiRoi, xinPhepRoiTrang } from "@/lib/admin/shared/unsaved-changes-guard";
import { useTheme } from "@/lib/admin/shared/use-theme";

/**
 * Sidebar theo mẫu GoClaw. Từ lg trở lên: cột cố định trong layout.
 * Dưới lg: drawer trượt từ trái, mở bằng nút hamburger ở topbar mobile.
 *
 * `lg:h-screen` là BẮT BUỘC, không phải trang trí. Khung ngoài (`app-shell.tsx`) là
 * `min-h-[100dvh]` - chỉ đặt SÀN, không đặt trần - nên ở `lg:static` sidebar
 * cao bằng nội dung tự nhiên của nó. Cửa sổ thấp hơn ngần đó là cả document
 * cuộn theo: sidebar trôi lên mất logo, và có HAI thanh cuộn dọc chồng nhau
 * (một của `<main>`, một của trang). `overflow-y-auto` của `<nav>` dưới đây
 * KHÔNG tự cứu được: `min-height: auto` chỉ triệt tiêu khi cha có chiều cao
 * xác định, mà ở desktop không ai cấp. Mobile không dính vì `fixed inset-y-0`
 * đã là chiều cao xác định sẵn.
 */
export function SidebarNav({
  sections,
  online,
  user,
  onLogout,
  mobileOpen,
  onCloseMobile,
}: {
  sections: NavSection[];
  /** Có ít nhất 1 account Zalo đang chạy - cho chấm trạng thái ở footer */
  online: boolean;
  user: UserSummary;
  onLogout: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const { theme, toggle } = useTheme();
  const router = useRouter();
  const pathname = usePathname();

  /**
   * Chặn điều hướng khi trang đang mở còn thay đổi chưa lưu.
   *
   * `preventDefault()` phải gọi ĐỒNG BỘ, không chờ được promise - nên kiểm bằng
   * `coCanHoiTruocKhiRoi()` (đồng bộ) trước, rồi mới hỏi. Không có gì chưa lưu
   * thì đi thẳng theo hành vi mặc định của link, không đụng gì.
   */
  function chanNeuChuaLuu(e: MouseEvent<HTMLAnchorElement>, to: string): void {
    if (!coCanHoiTruocKhiRoi()) {
      onCloseMobile();
      return;
    }
    e.preventDefault();
    void xinPhepRoiTrang().then((ok) => {
      if (!ok) return;
      onCloseMobile();
      router.push(to);
    });
  }

  return (
    <>
      {/* Backdrop chỉ tồn tại ở mobile khi drawer mở */}
      {mobileOpen && (
        <button
          aria-label="Đóng menu"
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-[2px] lg:hidden"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-line bg-surface transition-transform duration-200 lg:static lg:z-auto lg:h-screen lg:w-60 lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Điều hướng chính"
      >
        <div className="flex items-center gap-2.5 px-5 pt-5 pb-4">
          <Link
            href="/"
            onClick={(e) => chanNeuChuaLuu(e, "/")}
            className="flex items-center gap-2.5"
            title="Về trang chính"
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- fixed 294x156 brand asset */}
            <img src="/pema-logo.png" alt="Pema" width={294} height={156} className="h-9 w-auto" />
            <span className="text-[15px] leading-tight font-bold tracking-tight text-ink">
              CSKH
              <span className="block text-[11px] font-medium tracking-normal text-ink-soft">
                Trợ lý AI
              </span>
            </span>
          </Link>
          <button
            onClick={onCloseMobile}
            aria-label="Đóng menu"
            className="ml-auto rounded-lg p-1.5 text-ink-soft hover:bg-tile lg:hidden"
          >
            <IconClose size={17} />
          </button>
        </div>

        <nav className="mt-1 flex-1 overflow-y-auto px-3">
          {sections.map((section) => (
            <div key={section.title} className="mb-5">
              <div className="px-2.5 pb-1.5 text-[11px] font-semibold tracking-[0.12em] text-ink-soft/70 uppercase">
                {section.title}
              </div>
              {section.items.map((item) => {
                const active = isActivePath(pathname, item.to);
                return (
                  <Link
                    key={item.to}
                    href={item.to}
                    aria-current={active ? "page" : undefined}
                    onClick={(e) => chanNeuChuaLuu(e, item.to)}
                    className={`mb-0.5 flex items-center gap-2.5 rounded-xl px-2.5 py-2.5 text-[14px] transition-colors lg:py-2 ${
                      active
                        ? "bg-brand-50 font-semibold text-brand-700"
                        : "text-ink-soft hover:bg-tile hover:text-ink"
                    }`}
                  >
                    <item.icon size={17} />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="border-t border-line px-4 py-3">
          <div className="mb-2 flex items-center gap-2.5">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-500 text-[13px] font-semibold text-white">
              {(user.display_name.trim()[0] ?? "?").toUpperCase()}
            </span>
            <div className="min-w-0">
              <div className="truncate text-[13px] font-semibold text-ink">{user.display_name}</div>
              <div className="truncate text-[11px] text-ink-soft">
                {ROLE_LABEL[user.role]} · {user.clinic_name}
              </div>
            </div>
          </div>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-2 text-[12px] text-ink-soft">
              <span
                className={`h-2 w-2 rounded-full ${online ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"}`}
              />
              {online ? "Đã kết nối" : "Ngoại tuyến"} · v{process.env.NEXT_PUBLIC_APP_VERSION}
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
