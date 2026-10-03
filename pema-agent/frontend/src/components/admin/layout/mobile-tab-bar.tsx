"use client";

// New for Pema (not in the original dashboard): the daily CSKH work is done on a phone, so the four
// operations screens get a bottom tab bar under lg, and everything else stays one tap away in the
// drawer ("Menu"). Touch targets are at least 48px (design skill, native rule applied to the web).
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { MouseEvent } from "react";

import { IconMenu } from "@/components/admin/shared/dashboard-icons";
import { isActivePath, type NavItem } from "@/lib/nav";
import { coCanHoiTruocKhiRoi, xinPhepRoiTrang } from "@/lib/admin/shared/unsaved-changes-guard";

export function MobileTabBar({ tabs, onOpenMenu }: { tabs: NavItem[]; onOpenMenu: () => void }) {
  const pathname = usePathname();
  const router = useRouter();

  function guard(e: MouseEvent<HTMLAnchorElement>, to: string): void {
    if (!coCanHoiTruocKhiRoi()) return;
    e.preventDefault();
    void xinPhepRoiTrang().then((ok) => ok && router.push(to));
  }

  return (
    <nav
      aria-label="Điều hướng nhanh"
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
    >
      {tabs.map((item) => {
        const active = isActivePath(pathname, item.to);
        return (
          <Link
            key={item.to}
            href={item.to}
            aria-current={active ? "page" : undefined}
            onClick={(e) => guard(e, item.to)}
            className={`flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-micro font-medium ${
              active ? "text-brand-500" : "text-ink-soft"
            }`}
          >
            <item.icon size={21} />
            {item.tabLabel ?? item.label}
          </Link>
        );
      })}
      <button
        type="button"
        onClick={onOpenMenu}
        className="flex min-h-14 flex-1 flex-col items-center justify-center gap-0.5 text-micro font-medium text-ink-soft"
      >
        <IconMenu size={21} />
        Menu
      </button>
    </nav>
  );
}
