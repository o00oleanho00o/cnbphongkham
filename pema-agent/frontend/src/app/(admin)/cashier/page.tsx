"use client";

// Thu ngân: the old web's `cashier` screen, the order half of it. The quick-order button and the banner open the
// order dialog (`QuickOrderDialog`), the order history lists every order (Xem / in, Sửa nháp), and the tiles count
// them next to the product catalog. `?patient=<id>` opens the dialog for that patient (entry from Patient 360),
// `?edit=<order id>` opens a draft for editing. Invoices and "Thu tiền" are the finance step (U6): the old
// "Hóa đơn & thanh toán" panel is replaced by a note until then. Who may do what is the BE's: `order.write` makes
// and edits drafts, `order.read` only looks.
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconPlus } from "@/components/admin/shared/dashboard-icons";
import {
  EmptyState,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { QuickOrderDialog } from "@/components/orders/quick-order-dialog";
import { http, unwrap } from "@/lib/api/client";
import {
  historyLine,
  orderErrorMessage,
  type CatalogSummary,
  type OrderRow,
  type OrderSummary,
} from "@/lib/orders/order-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button, buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { Tile } from "@/ui/tile";

const PAGE_SIZE = 12;

type CashierData = {
  summary: CatalogSummary;
  orders: OrderSummary[];
  total: number;
  drafts: number;
  approved: number;
};

type DialogState = { kind: "new"; patientId?: string } | { kind: "edit"; order: OrderRow } | null;

function OrderHistoryRow({
  order,
  canWrite,
  onEdit,
}: {
  order: OrderSummary;
  canWrite: boolean;
  onEdit: () => void;
}) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="text-body font-semibold text-ink">{order.patient_name}</p>
        <p className="text-small text-ink-soft">{historyLine(order)}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={order.status === "approved" ? "success" : "warning"}>
          {order.status === "approved" ? "Đã duyệt" : "Bản nháp"}
        </Badge>
        <Link
          href={`/orders/${order.id}`}
          className={buttonClass("secondary")}
          aria-label={`Xem / in đơn của ${order.patient_name}`}
        >
          Xem / in
        </Link>
        {canWrite && order.status === "draft" && (
          <Button
            variant="secondary"
            onClick={onEdit}
            aria-label={`Sửa nháp đơn của ${order.patient_name}`}
          >
            Sửa nháp
          </Button>
        )}
      </div>
    </li>
  );
}

function CashierPage() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { can } = useSession();
  const canWrite = can("order.write");
  const [page, setPage] = useState(0);
  const [dialog, setDialog] = useState<DialogState>(null);
  const presetPatient = params.get("patient");
  const presetEdit = params.get("edit");

  const load = useCallback(
    async (signal: AbortSignal): Promise<CashierData> => {
      const ask = (status?: "draft" | "approved", limit = PAGE_SIZE, offset = 0) =>
        unwrap(
          http.GET("/api/v1/orders", { params: { query: { status, limit, offset } }, signal }),
        );
      const [summary, orders, drafts, approved] = await Promise.all([
        unwrap(http.GET("/api/v1/catalog/summary", { signal })),
        ask(undefined, PAGE_SIZE, page * PAGE_SIZE),
        ask("draft", 1),
        ask("approved", 1),
      ]);
      return {
        summary,
        orders: orders.items,
        total: orders.total,
        drafts: drafts.total,
        approved: approved.total,
      };
    },
    [page],
  );
  const { data, error, loading, reload } = useLoad(load);

  const closeDialog = useCallback(() => {
    setDialog(null);
    if (presetPatient !== null || presetEdit !== null) router.replace("/cashier");
  }, [presetPatient, presetEdit, router]);

  const openDraft = useCallback(
    async (orderId: string) => {
      try {
        const order = await unwrap(
          http.GET("/api/v1/orders/{order_id}", { params: { path: { order_id: orderId } } }),
        );
        if (!order.editable) {
          toast.push(
            "error",
            order.status === "approved"
              ? "Chỉ được sửa đơn nháp còn tồn tại."
              : "Đơn đã thu tiền; không thể sửa.",
          );
          return;
        }
        setDialog({ kind: "edit", order });
      } catch (err) {
        toast.push("error", orderErrorMessage(err));
      }
    },
    [toast],
  );

  // An address with `?patient=` or `?edit=` opens the dialog once.
  useEffect(() => {
    if (!canWrite) return;
    if (presetEdit !== null) {
      void openDraft(presetEdit);
      return;
    }
    if (presetPatient !== null) setDialog({ kind: "new", patientId: presetPatient });
  }, [canWrite, presetEdit, presetPatient, openDraft]);

  function saved(order: OrderRow) {
    setDialog(null);
    router.push(`/orders/${order.id}`);
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  return (
    <div>
      <PageHeader
        title="Thu ngân"
        subtitle="Thu tiền và lên đơn nhanh theo mẫu PEMA."
        aside={
          canWrite ? (
            <PrimaryButton onClick={() => setDialog({ kind: "new" })}>
              <IconPlus size={16} />
              Lên đơn nhanh
            </PrimaryButton>
          ) : undefined
        }
      />

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={4} />}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3.5 xl:grid-cols-4">
            <Tile label="Tổng số đơn" value={data.total} note="Nháp và đã duyệt" />
            <Tile label="Bản nháp" value={data.drafts} note="Chờ bác sĩ duyệt" tone="warning" />
            <Tile label="Đã duyệt" value={data.approved} note="Bác sĩ đã duyệt" tone="success" />
            <Tile
              label="Catalog sản phẩm"
              value={data.summary.total}
              note={
                data.summary.source_name ? `Từ ${data.summary.source_name}` : "Chưa nhập catalog"
              }
            />
          </div>

          {canWrite && (
            <Card
              title="Lên đơn theo mẫu PEMA"
              subtitle="Thuốc vào Đơn thuốc; mỹ phẩm, TPCN và loại khác vào Phiếu tư vấn. Bản in A5 dọc."
              aside={
                <PrimaryButton onClick={() => setDialog({ kind: "new" })}>
                  Mở form lên đơn nhanh →
                </PrimaryButton>
              }
              className="bg-tile/50"
            >
              {null}
            </Card>
          )}

          <Card title="Hóa đơn & thanh toán">
            <Notice>
              Hóa đơn và thu tiền nằm ở bước Tài chính. Đơn đã lập ở đây là căn cứ để lập hóa đơn;
              duyệt đơn không có nghĩa là đã cấp thuốc.
            </Notice>
          </Card>

          <Card
            title="Đơn thuốc & phiếu tư vấn"
            subtitle="Nháp → bác sĩ duyệt → in và hiển thị trên app"
          >
            {data.orders.length === 0 ? (
              <EmptyState title="Chưa có đơn từ catalog." />
            ) : (
              <ul className="divide-y divide-line">
                {data.orders.map((order) => (
                  <OrderHistoryRow
                    key={order.id}
                    order={order}
                    canWrite={canWrite}
                    onEdit={() => void openDraft(order.id)}
                  />
                ))}
              </ul>
            )}
            {data.total > PAGE_SIZE && (
              <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
                <span className="text-small text-ink-soft">
                  {data.total} đơn · Trang {page + 1}/{pages}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                  >
                    ← Trước
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={page + 1 >= pages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Sau →
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {dialog !== null && (
        <QuickOrderDialog
          presetPatientId={dialog.kind === "new" ? dialog.patientId : undefined}
          editing={dialog.kind === "edit" ? dialog.order : null}
          onClose={closeDialog}
          onSaved={saved}
          onStale={reload}
        />
      )}
    </div>
  );
}

export default function CashierRoute() {
  return (
    <Suspense fallback={<ListSkeleton rows={4} />}>
      <CashierPage />
    </Suspense>
  );
}
