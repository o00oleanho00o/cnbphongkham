"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ComponentProps, MouseEvent } from "react";

import { coCanHoiTruocKhiRoi, xinPhepRoiTrang } from "@/lib/admin/shared/unsaved-changes-guard";

type GuardedLinkProps = Omit<ComponentProps<typeof Link>, "href" | "onClick"> & {
  href: string;
  /** Runs when the navigation really happens (e.g. close the mobile drawer). */
  onNavigate?: () => void;
};

/**
 * Link that asks before leaving a page with unsaved changes.
 *
 * `preventDefault()` must run synchronously, so the synchronous check (`coCanHoiTruocKhiRoi`) comes first:
 * with nothing unsaved the link behaves like any other link; otherwise it waits for the user's answer.
 */
export function GuardedLink({ href, onNavigate, ...rest }: GuardedLinkProps) {
  const router = useRouter();

  function onClick(e: MouseEvent<HTMLAnchorElement>): void {
    if (!coCanHoiTruocKhiRoi()) {
      onNavigate?.();
      return;
    }
    e.preventDefault();
    void xinPhepRoiTrang().then((ok) => {
      if (!ok) return;
      onNavigate?.();
      router.push(href);
    });
  }

  return <Link href={href} onClick={onClick} {...rest} />;
}
