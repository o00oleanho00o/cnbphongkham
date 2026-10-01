"use client";

// List + detail layout of Inbox and the review queue. On a phone the detail is a CHILD SCREEN (the list
// disappears while an item is open, a back button returns), as the project's mobile rule asks; from `lg`
// both panes show side by side so the list stays visible while reading.
import type { ReactNode } from "react";

import { IconChevronLeft } from "@/components/admin/shared/ops-icons";

export function MasterDetail({
  list,
  detail,
  detailOpen,
  onBack,
  backLabel,
  emptyDetail,
}: {
  list: ReactNode;
  detail: ReactNode;
  detailOpen: boolean;
  onBack: () => void;
  backLabel: string;
  emptyDetail: ReactNode;
}) {
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(320px,400px)_minmax(0,1fr)] xl:grid-cols-[420px_minmax(0,1fr)]">
      <div className={detailOpen ? "hidden lg:block" : "block"}>{list}</div>
      <div className={detailOpen ? "block" : "hidden lg:block"}>
        {detailOpen ? (
          <div>
            <button
              type="button"
              onClick={onBack}
              className="mb-3 inline-flex min-h-11 items-center gap-1 text-[14px] font-medium text-brand-500 hover:text-brand-600 lg:hidden"
            >
              <IconChevronLeft size={18} />
              {backLabel}
            </button>
            {detail}
          </div>
        ) : (
          emptyDetail
        )}
      </div>
    </div>
  );
}
