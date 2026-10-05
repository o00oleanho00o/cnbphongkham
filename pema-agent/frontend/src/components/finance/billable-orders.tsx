"use client";

// Quick orders (U5) that have something to pay and no invoice yet, with "Lập hóa đơn": the invoice is the order's
// total, raised once (asking again returns the same one). Old web: `order-data.js` `saveOrder` rewrote an invoice
// with every save; here the cashier raises it on purpose. Shared by the cashier and `/finance/payments`.
import Link from "next/link";
import { useState } from "react";

import { Notice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import { financeErrorMessage, formatVnd, type BillableOrder } from "@/lib/finance/finance-view";
import { Badge } from "@/ui/badge";
import { Button, buttonClass } from "@/ui/button";

export function BillableOrders({
  orders,
  canRaise,
  onRaised,
}: {
  orders: readonly BillableOrder[];
  canRaise: boolean;
  onRaised: () => void;
}) {
  const toast = useToast();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  async function raise(order: BillableOrder) {
    setProblem("");
    setBusyId(order.order_id);
    try {
      await unwrap(
        http.POST("/api/v1/finance/invoices/from-order", { body: { order_id: order.order_id } }),
      );
      toast.push("success", "Đã lập hóa đơn cho đơn.");
      onRaised();
    } catch (error) {
      setProblem(financeErrorMessage(error));
    } finally {
      setBusyId(null);
    }
  }

  if (orders.length === 0) return null;
  return (
    <section aria-label="Đơn chưa có hóa đơn" className="mt-4 border-t border-line pt-4">
      <h3 className="text-small font-semibold text-heading">Đơn sản phẩm chưa có hóa đơn</h3>
      <p className="mb-2 text-label text-ink-soft">
        Hóa đơn của đơn lấy theo tổng tiền đơn; lập một lần. Duyệt đơn không có nghĩa là đã cấp
        thuốc.
      </p>
      {problem !== "" && (
        <div className="mb-2">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
      <ul className="divide-y divide-line">
        {orders.map((order) => (
          <li
            key={order.order_id}
            className="flex flex-wrap items-center justify-between gap-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="text-body font-semibold text-ink">{order.patient_name}</p>
              <p className="text-small text-ink-soft">
                {order.patient_code} · {order.order_date} · {formatVnd(order.total_vnd)}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={order.status === "approved" ? "success" : "warning"}>
                {order.status === "approved" ? "Đã duyệt" : "Bản nháp"}
              </Badge>
              <Link
                href={`/orders/${order.order_id}`}
                className={buttonClass("quiet")}
                aria-label={`In tách đơn của ${order.patient_name}`}
              >
                In tách đơn
              </Link>
              {canRaise && (
                <Button
                  variant="secondary"
                  disabled={busyId === order.order_id}
                  onClick={() => void raise(order)}
                  aria-label={`Lập hóa đơn cho đơn của ${order.patient_name}`}
                >
                  Lập hóa đơn
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
