"use client";

// Bản in A5 của một đơn. Old web: `order-review.js` (`data-print` filter, `beforeprint`) and `order-review.css`.
// Only the sheets print: the menu, the top bar and this toolbar are hidden by the print stylesheet, each sheet starts
// on its own A5 page and a long usage flows on to the next page (natural flow, no height cap). A draft carries the
// draft mark on screen and prints nothing, only a note that the doctor has not approved it. `?sheet=` picks
// PRESCRIPTION, CONSULTATION or both. The page never prints by itself: the button does.
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect } from "react";

import { ListSkeleton, Notice } from "@/components/ops/ops-ui";
import { OrderSheets } from "@/components/orders/order-sheet";
import { http, unwrap } from "@/lib/api/client";
import { DRAFT_MARK } from "@/lib/orders/order-view";
import { useLoad } from "@/lib/use-load";
import { Button, buttonClass } from "@/ui/button";

type Sheet = "PRESCRIPTION" | "CONSULTATION" | "all";

function asSheet(value: string | null): Sheet {
  return value === "PRESCRIPTION" || value === "CONSULTATION" ? value : "all";
}

const SHEET_LABEL: Record<Sheet, string> = {
  PRESCRIPTION: "In đơn thuốc",
  CONSULTATION: "In phiếu tư vấn",
  all: "In tất cả",
};

function OrderPrintPage() {
  const { id } = useParams<{ id: string }>();
  const sheet = asSheet(useSearchParams().get("sheet"));
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/orders/{order_id}/print-data", {
          params: { path: { order_id: id } },
          signal,
        }),
      ),
    [id],
  );
  const { data, error } = useLoad(load);

  useEffect(() => {
    if (data) document.title = `Tách đơn – ${data.patient.full_name}`;
  }, [data]);

  async function print() {
    // the sheets use the page font: wait for it so the print preview does not fall back (older engines: no `fonts`)
    if ("fonts" in document) await document.fonts.ready;
    window.print();
  }

  if (error && !data) {
    return (
      <div role="alert" className="text-body text-danger">
        {error}
      </div>
    );
  }
  if (!data) return <ListSkeleton rows={3} />;

  return (
    <div className="order-print-root" data-approved={String(data.printable)} data-sheet={sheet}>
      <div className="order-screen-only mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-title font-bold text-heading">
            Bản in A5 · {data.patient.full_name}
          </h1>
          <p className="text-small text-ink-soft">
            A5 dọc 148 × 210 mm. Tắt đầu trang và chân trang của trình duyệt nếu đang bật.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={!data.printable} onClick={() => void print()}>
            {SHEET_LABEL[sheet]}
          </Button>
          <Link href={`/orders/${id}`} className={buttonClass("secondary")}>
            Về tách đơn
          </Link>
        </div>
      </div>
      {!data.printable && (
        <div className="order-screen-only mb-4">
          <Notice tone="warn">{DRAFT_MARK} — chưa được bác sĩ duyệt để phát hành.</Notice>
        </div>
      )}
      <OrderSheets print={data} />
      <p className="order-print-blocked">{DRAFT_MARK}. Đơn nháp cần bác sĩ duyệt trước khi in.</p>
    </div>
  );
}

export default function OrderPrintRoute() {
  return (
    <Suspense fallback={<ListSkeleton rows={3} />}>
      <OrderPrintPage />
    </Suspense>
  );
}
