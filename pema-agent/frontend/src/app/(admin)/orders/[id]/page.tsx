"use client";

// Tách đơn: the review of an order before it is printed. Old web: `order-review/index.html` + `order-review.js`.
// The two A5 sheets side by side (Đơn thuốc, Phiếu tư vấn), the lines that are not printed or still need a class
// listed under them, and the buttons: print one sheet or both (only once a doctor approved and every line is
// classified), "Bác sĩ duyệt & gửi app" (only the responsible doctor, or the owner), back to the cashier. A draft
// prints nothing and is not shown on the patient app. The rules are the BE's (`pema.clinic.actions.orders`).
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { ListSkeleton, Notice, PrimaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { OrderSheets } from "@/components/orders/order-sheet";
import { http, unwrap } from "@/lib/api/client";
import {
  excludedNote,
  orderErrorMessage,
  orderStale,
  reviewStatusLine,
  showApprove,
  unresolvedNote,
  type OrderPrint,
} from "@/lib/orders/order-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Button, buttonClass } from "@/ui/button";

type Sheet = "PRESCRIPTION" | "CONSULTATION" | "all";

const PRINT_BUTTONS: readonly { sheet: Sheet; label: string }[] = [
  { sheet: "PRESCRIPTION", label: "In đơn thuốc" },
  { sheet: "CONSULTATION", label: "In phiếu tư vấn" },
  { sheet: "all", label: "In tất cả" },
];

function sheetCount(print: OrderPrint, sheet: Sheet): number {
  if (sheet === "PRESCRIPTION") return print.prescription.length;
  if (sheet === "CONSULTATION") return print.consultation.length;
  return print.prescription.length + print.consultation.length;
}

export default function OrderReviewPage() {
  const { id } = useParams<{ id: string }>();
  const toast = useToast();
  const { user, can } = useSession();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

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
  const { data, error, reload } = useLoad(load);

  async function approve(print: OrderPrint) {
    setProblem("");
    setBusy(true);
    try {
      await unwrap(
        http.POST("/api/v1/orders/{order_id}/approve", {
          params: { path: { order_id: print.order.id } },
          body: { version: print.order.version },
        }),
      );
      toast.push("success", "Đã duyệt đơn. Có thể in hai phiếu.");
      reload();
    } catch (err) {
      setProblem(orderErrorMessage(err));
      if (orderStale(err)) reload();
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) {
    return (
      <div>
        <PageHeader title="Tách đơn" subtitle="Không mở được đơn này." />
        <div role="alert" className="mb-4 text-body text-danger">
          {error}
        </div>
        <Link href="/cashier" className={buttonClass("secondary")}>
          Về thu ngân
        </Link>
      </div>
    );
  }
  if (!data) return <ListSkeleton rows={3} />;

  const { order } = data;
  const canApprove = showApprove(order, user, can("order.approve"));
  const unresolved = unresolvedNote(data);
  const excluded = excludedNote(data);
  return (
    <div>
      <PageHeader
        title={`Tách đơn – ${data.patient.full_name}`}
        subtitle={reviewStatusLine(order)}
        aside={
          <>
            {PRINT_BUTTONS.map(({ sheet, label }) =>
              data.printable && sheetCount(data, sheet) > 0 ? (
                <Link
                  key={sheet}
                  href={`/orders/${order.id}/print?sheet=${sheet}`}
                  target="_blank"
                  className={buttonClass("secondary")}
                >
                  {label}
                </Link>
              ) : (
                <Button key={sheet} variant="secondary" disabled>
                  {label}
                </Button>
              ),
            )}
            {canApprove && (
              <PrimaryButton
                onClick={() => void approve(data)}
                disabled={busy || order.unresolved_count > 0}
              >
                {busy ? "Đang duyệt..." : "Bác sĩ duyệt & gửi app"}
              </PrimaryButton>
            )}
            {order.editable && can("order.write") && (
              <Link href={`/cashier?edit=${order.id}`} className={buttonClass("secondary")}>
                Sửa nháp
              </Link>
            )}
            <Link href="/cashier" className={buttonClass("secondary")}>
              Về thu ngân
            </Link>
          </>
        }
      />
      {problem !== "" && (
        <div className="mb-4" id="review-error">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
      {order.status === "draft" && (
        <div className="mb-4">
          <Notice tone="warn">
            Đơn nháp cần bác sĩ duyệt trước khi in. Nháp chưa hiển thị trên app.
          </Notice>
        </div>
      )}
      <div className="order-print-root">
        <OrderSheets print={data} />
      </div>
      <div className="mt-4 space-y-2">
        {unresolved && <Notice tone="warn">{unresolved}</Notice>}
        {excluded && <Notice>{excluded}</Notice>}
      </div>
    </div>
  );
}
