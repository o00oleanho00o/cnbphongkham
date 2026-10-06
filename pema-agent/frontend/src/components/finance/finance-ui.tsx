"use client";

// Small pieces the finance pages share: the tab bar between the screens, the status chip, the line shown while a
// page loads and the pair "error with retry".
import Link from "next/link";
import type { ReactNode } from "react";

import { RetryNotice } from "@/components/ops/ops-ui";
import {
  STATUS_LABEL,
  STATUS_TONE,
  financeHref,
  notConnected,
  tabOfPath,
  visibleTabs,
  type EntryStatus,
  type FinanceScope,
  type PeriodStatus,
} from "@/lib/finance/finance-view";
import { Badge } from "@/ui/badge";
import { cx } from "@/ui/classnames";

/** Tabs between the screens of the finance area; the month and the projection travel with every link. */
export function FinanceTabs({
  pathname,
  month,
  scope,
}: {
  pathname: string;
  month: string;
  scope: FinanceScope;
}) {
  const current = tabOfPath(pathname);
  return (
    <nav
      aria-label="Phân hệ tài chính"
      className="-mx-4 mb-5 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0"
    >
      {visibleTabs(scope).map((tab) => {
        const active = tab.id === current;
        return (
          <Link
            key={tab.id}
            href={financeHref(tab.href, month, scope)}
            aria-current={active ? "page" : undefined}
            className={cx(
              "-mb-px inline-flex min-h-11 items-center border-b-2 px-3.5 text-body whitespace-nowrap lg:min-h-10",
              active
                ? "border-link font-bold text-link"
                : "border-transparent text-ink-soft hover:text-ink",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

/** The chip of a month ("Đang đối soát", "Đã chốt tháng", "Đã chi") or of an entry ("Chờ duyệt", "Đã duyệt"). */
export function StatusBadge({ status }: { status: PeriodStatus | EntryStatus }) {
  return (
    <Badge tone={STATUS_TONE[status]} dot={false}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

/** The old "Đang tải dữ liệu…" line. */
export function LoadingLine() {
  return (
    <p role="status" aria-live="polite" className="py-6 text-body text-ink-soft">
      Đang tải dữ liệu…
    </p>
  );
}

/** "Chưa kết nối dữ liệu tài chính: <reason>" with the retry button, and the loading line before any data. */
export function LoadState({
  error,
  loading,
  hasData,
  onRetry,
  children,
}: {
  error: string;
  loading: boolean;
  hasData: boolean;
  onRetry: () => void;
  children?: ReactNode;
}) {
  return (
    <>
      {error !== "" && <RetryNotice message={notConnected(error)} onRetry={onRetry} />}
      {loading && !hasData && <LoadingLine />}
      {children}
    </>
  );
}
