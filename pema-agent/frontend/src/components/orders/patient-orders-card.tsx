"use client";

// "Đơn thuốc & phiếu tư vấn" of one patient, at the bottom of the Kế hoạch tab of Patient 360. Old web: the
// "Tạo đơn nháp" entry of the plan tab and the order history of the patient (`order-ui.js` `history(p)`), plus the
// approved orders grouped the way the old Patient Mobile showed them (Đơn thuốc, Phiếu tư vấn). The grouped list is
// the STAFF view of what the app will show; nothing here is shown to the patient yet (a later step).
import Link from "next/link";
import { useCallback } from "react";

import { EmptyState, ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import {
  ROUTE_LABEL,
  historyLine,
  type ApprovedGroup,
  type OrderItemRow,
} from "@/lib/orders/order-view";
import { formatDate } from "@/lib/ops/format";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";

function SheetLines({ title, items }: { title: string; items: readonly OrderItemRow[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-small font-semibold text-heading">{title}</h4>
      <ul className="mt-1 space-y-1">
        {items.map((item) => (
          <li key={item.line_no} className="text-small text-ink">
            {item.name} × {item.quantity} {item.unit}
            <span className="block text-label whitespace-pre-line text-ink-soft">{item.usage}</span>
            {item.note !== "" && (
              <span className="block text-label text-ink-soft">Ghi chú: {item.note}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function AppPreview({ groups }: { groups: readonly ApprovedGroup[] }) {
  if (groups.length === 0) return null;
  return (
    <section aria-label="Hiển thị trên app" className="mt-4 border-t border-line pt-3">
      <h3 className="text-small font-semibold text-heading">
        Hiển thị trên app (xem trước cho nhân viên)
      </h3>
      <p className="mb-2 text-label text-ink-soft">
        Chỉ đơn đã duyệt; sản phẩm “Không in” và sản phẩm chưa phân loại không hiện.
      </p>
      <div className="space-y-3">
        {groups.map((group) => (
          <article key={group.order_id} className="rounded-control border border-line p-3">
            <p className="text-small font-semibold text-ink">
              {formatDate(group.order_date)} · {group.doctor_name}
            </p>
            <div className="mt-2 space-y-2">
              <SheetLines title={ROUTE_LABEL.PRESCRIPTION} items={group.prescription} />
              <SheetLines title={ROUTE_LABEL.CONSULTATION} items={group.consultation} />
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function PatientOrdersCard({ patientId }: { patientId: string }) {
  const { can } = useSession();
  const canWrite = can("order.write");
  const load = useCallback(
    async (signal: AbortSignal) => {
      const [orders, approved] = await Promise.all([
        unwrap(
          http.GET("/api/v1/orders", {
            params: { query: { patient_id: patientId, limit: 50 } },
            signal,
          }),
        ),
        unwrap(
          http.GET("/api/v1/patients/{patient_id}/approved-orders", {
            params: { path: { patient_id: patientId } },
            signal,
          }),
        ),
      ]);
      return { orders: orders.items, approved };
    },
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);

  return (
    <Card
      title="Đơn thuốc & phiếu tư vấn"
      subtitle="Nháp → bác sĩ duyệt → in và hiển thị trên app"
      aside={
        canWrite ? (
          <Link href={`/cashier?patient=${patientId}`} className={buttonClass("primary")}>
            Tạo đơn nháp
          </Link>
        ) : undefined
      }
    >
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={2} />}
      {data && data.orders.length === 0 && (
        <EmptyState title="Chưa có đơn nào cho bệnh nhân này." />
      )}
      {data && data.orders.length > 0 && (
        <ul className="divide-y divide-line">
          {data.orders.map((order) => (
            <li key={order.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
              <p className="text-small text-ink">{historyLine(order)}</p>
              <div className="flex items-center gap-2">
                <Badge tone={order.status === "approved" ? "success" : "warning"}>
                  {order.status === "approved" ? "Đã duyệt" : "Bản nháp"}
                </Badge>
                <Link href={`/orders/${order.id}`} className={buttonClass("secondary")}>
                  Xem / in
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
      {data && <AppPreview groups={data.approved} />}
    </Card>
  );
}
