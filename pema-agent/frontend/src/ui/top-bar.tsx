"use client";

// Top bar of the old Pema Clinic Web: breadcrumbs ("Không gian phòng khám / <screen>") on the left, patient
// search and the notification bell on the right (60px, 64px from 1600px). Below `lg` the sidebar is a drawer,
// so the bar carries the menu button and the logo instead (the bottom tab bar holds the daily screens).
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { IconMenu, IconSearch } from "@/components/admin/shared/dashboard-icons";
import { coCanHoiTruocKhiRoi, xinPhepRoiTrang } from "@/lib/admin/shared/unsaved-changes-guard";

import { GuardedLink } from "./guarded-link";
import { IconBell } from "./icons";

export function TopBar({
  title,
  clinicName,
  onOpenMenu,
  searchHref,
  bellHref,
}: {
  /** Name of the current screen (breadcrumb); empty when the path is not in the menu. */
  title: string;
  clinicName: string;
  onOpenMenu: () => void;
  /** Where the patient search goes (`?q=` is appended); omitted when the role cannot search patients. */
  searchHref?: string;
  /** Where the bell goes; omitted when the role has no inbox. */
  bellHref?: string;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  function submitSearch(e: FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (searchHref === undefined || query.trim() === "") return;
    const target = `${searchHref}?q=${encodeURIComponent(query.trim())}`;
    if (!coCanHoiTruocKhiRoi()) {
      router.push(target);
      return;
    }
    void xinPhepRoiTrang().then((ok) => {
      if (ok) router.push(target);
    });
  }

  return (
    <header className="sticky top-0 z-(--z-topbar) flex h-(--layout-topbar-h) shrink-0 items-center justify-between gap-3 border-b border-line bg-surface/90 px-4 backdrop-blur lg:px-(--layout-content-pad-x) wide:h-(--layout-topbar-h-wide) print:hidden">
      <div className="flex min-w-0 items-center gap-3">
        <button
          onClick={onOpenMenu}
          aria-label="Mở menu"
          className="-ml-1.5 rounded-lg p-2 text-ink-soft hover:bg-tile hover:text-ink lg:hidden"
        >
          <IconMenu size={20} />
        </button>
        <GuardedLink href="/" className="flex items-center gap-2 lg:hidden" title="Về trang chính">
          {/* eslint-disable-next-line @next/next/no-img-element -- fixed brand asset */}
          <img src="/pema-logo.png" alt="Pema" width={294} height={156} className="h-7 w-auto" />
          <span className="truncate text-body-lg font-semibold text-ink">
            {clinicName.trim() || "CSKH"}
          </span>
        </GuardedLink>
        <nav
          aria-label="Vị trí"
          className="hidden min-w-0 items-center gap-2 text-body text-ink-soft lg:flex"
        >
          <span>Không gian phòng khám</span>
          {title !== "" && (
            <>
              <span aria-hidden>/</span>
              <strong className="truncate font-semibold text-ink">{title}</strong>
            </>
          )}
        </nav>
      </div>

      <div className="hidden items-center gap-2 lg:flex">
        {searchHref !== undefined && (
          <form
            role="search"
            onSubmit={submitSearch}
            className="flex w-64 items-center gap-2 rounded-tile border border-line-strong bg-field px-3 py-2 text-ink-soft focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100"
          >
            <IconSearch size={15} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Tìm bệnh nhân"
              placeholder="Tìm bệnh nhân..."
              className="w-full bg-transparent text-label text-ink outline-none placeholder:text-ink-soft"
            />
          </form>
        )}
        {bellHref !== undefined && (
          <GuardedLink
            href={bellHref}
            aria-label="Mở thông báo"
            className="rounded-tile p-2 text-ink-soft hover:bg-brand-50 hover:text-brand-700"
          >
            <IconBell size={19} />
          </GuardedLink>
        )}
      </div>
    </header>
  );
}
