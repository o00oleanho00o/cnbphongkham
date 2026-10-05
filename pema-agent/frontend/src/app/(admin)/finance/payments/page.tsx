"use client";

// Phiếu thu & thông báo (old web: `finance.js` `receipts()`): "Thu tiền khách hàng" (an open invoice, the amount,
// the method, "Xác nhận thu"), "Giao dịch trong kỳ" and, for the owner alone, "Thông báo của chủ phòng khám" with
// "Đã đọc". The accountant is told "Kế toán không đọc inbox của chủ." Here every invoice is collected in this app
// (the old page refused the ones of the old cashier), a receipt is idempotent and never exceeds the balance, and the
// quick orders without an invoice are listed under the form with "Lập hóa đơn".
import { useCallback, useMemo, useState } from "react";

import { BillableOrders } from "@/components/finance/billable-orders";
import { useFinance } from "@/components/finance/finance-context";
import { LoadState } from "@/components/finance/finance-ui";
import { PaymentFields } from "@/components/finance/payment-dialog";
import { Notice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  METHOD_LABEL,
  NO_PAYMENTS,
  dueChoiceLabel,
  financeErrorMessage,
  formatVnd,
  notificationTime,
  type BillableOrder,
  type InvoiceRow,
  type NotificationRow,
  type PaymentRow,
} from "@/lib/finance/finance-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

const PAYMENT_LIMIT = 20;

type PaymentsData = {
  due: InvoiceRow[];
  payments: { items: PaymentRow[]; total: number };
  notifications: NotificationRow[];
  billable: BillableOrder[];
};

function CollectCard({
  due,
  payments,
  total,
  onPaid,
}: {
  due: readonly InvoiceRow[];
  payments: readonly PaymentRow[];
  total: number;
  onPaid: () => void;
}) {
  const toast = useToast();
  const [invoiceId, setInvoiceId] = useState("");
  const chosen = due.find((i) => i.id === invoiceId) ?? due[0];
  return (
    <Card title="Thu tiền khách hàng">
      <Field label="Hóa đơn còn nợ">
        {(control) => (
          <select
            {...control}
            value={chosen?.id ?? ""}
            onChange={(e) => setInvoiceId(e.target.value)}
            className={FIELD_CONTROL_CLASS}
            disabled={due.length === 0}
          >
            {due.map((invoice) => (
              <option key={invoice.id} value={invoice.id}>
                {dueChoiceLabel(invoice)}
              </option>
            ))}
          </select>
        )}
      </Field>
      {chosen ? (
        <PaymentFields
          key={`${chosen.id}:${chosen.due_vnd}`}
          invoice={chosen}
          amountLabel="Số thu"
          submitLabel="Xác nhận thu"
          onPaid={() => {
            toast.push("success", "Đã ghi phiếu thu và cập nhật hóa đơn");
            onPaid();
          }}
        />
      ) : (
        <Button disabled>Xác nhận thu</Button>
      )}
      <p className="mt-3 text-small text-ink-soft">
        Mỗi lần thu có một mã chống thu trùng: bấm lại sau khi mất kết nối không tạo phiếu thứ hai.
        Không thu quá số còn nợ.
      </p>
      <h3 className="mt-4 text-body-lg font-bold text-heading">Giao dịch trong kỳ</h3>
      {payments.length === 0 ? (
        <p className="py-2 text-body text-ink-soft">{NO_PAYMENTS}</p>
      ) : (
        <ul className="divide-y divide-line">
          {payments.map((payment) => (
            <li key={payment.id} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-body text-ink">{payment.patient_code}</p>
                <p className="text-small text-ink-soft">
                  {payment.paid_on} · {METHOD_LABEL[payment.method]} · {payment.invoice_number}
                </p>
              </div>
              <strong className="text-body-lg text-heading tabular-nums">
                {formatVnd(payment.amount_vnd)}
              </strong>
            </li>
          ))}
        </ul>
      )}
      {total > payments.length && (
        <p className="mt-1 text-label text-ink-soft">
          {payments.length} phiếu gần nhất trên tổng {total} phiếu của kỳ.
        </p>
      )}
    </Card>
  );
}

function NotificationsCard({
  canRead,
  notifications,
  onRead,
}: {
  canRead: boolean;
  notifications: readonly NotificationRow[];
  onRead: () => void;
}) {
  const [problem, setProblem] = useState("");
  async function markRead(id: string) {
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/finance/notifications/{notification_id}/read", {
          params: { path: { notification_id: id } },
        }),
      );
      onRead();
    } catch (error) {
      setProblem(financeErrorMessage(error));
    }
  }
  return (
    <Card title="Thông báo của chủ phòng khám">
      {!canRead && <p className="text-body text-ink">Kế toán không đọc inbox của chủ.</p>}
      {canRead && problem !== "" && <Notice tone="error">{problem}</Notice>}
      {canRead && notifications.length === 0 && (
        <p className="text-body text-ink">Thanh toán thành công sẽ xuất hiện tại đây.</p>
      )}
      {canRead && (
        <ul className="divide-y divide-line">
          {notifications.map((note) => (
            <li key={note.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="text-body font-semibold text-ink">{note.title}</p>
                <p className="text-body text-ink">{note.body}</p>
                <p className="text-label text-ink-soft">{notificationTime(note.created_at)}</p>
              </div>
              {note.read ? (
                <span className="text-small text-ink-soft">Đã đọc</span>
              ) : (
                <Button
                  variant="secondary"
                  onClick={() => void markRead(note.id)}
                  aria-label={`Đã đọc: ${note.body}`}
                >
                  Đã đọc
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function FinancePaymentsPage() {
  const { month, canCollect, refreshKey, reload } = useFinance();
  const { can } = useSession();
  const canReadNotes = can("finance.notifications");
  const load = useCallback(
    async (signal: AbortSignal): Promise<PaymentsData> => {
      void refreshKey; // "Làm mới" and every change raise it: a new load function means "fetch again"
      const [due, payments, notifications, billable] = await Promise.all([
        unwrap(
          http.GET("/api/v1/finance/invoices", {
            params: { query: { due_only: true, limit: 200 } },
            signal,
          }),
        ),
        unwrap(
          http.GET("/api/v1/finance/payments", {
            params: { query: { month, limit: PAYMENT_LIMIT } },
            signal,
          }),
        ),
        canReadNotes
          ? unwrap(http.GET("/api/v1/finance/notifications", { signal }))
          : Promise.resolve([] as NotificationRow[]),
        unwrap(http.GET("/api/v1/finance/billable-orders", { signal })),
      ]);
      return { due: due.items, payments, notifications, billable };
    },
    [month, canReadNotes, refreshKey],
  );
  const { data, error, loading, reload: retry } = useLoad(load);
  const payments = useMemo(() => data?.payments.items ?? [], [data]);

  return (
    <div className="space-y-4">
      <LoadState error={error} loading={loading} hasData={data !== undefined} onRetry={retry} />
      {data && (
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            {canCollect ? (
              <CollectCard
                due={data.due}
                payments={payments}
                total={data.payments.total}
                onPaid={reload}
              />
            ) : (
              <Card title="Thu tiền khách hàng">
                <Notice tone="warn">Vai trò của bạn không được ghi phiếu thu.</Notice>
              </Card>
            )}
            {data.billable.length > 0 && (
              <div className="mt-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5 [&>section]:mt-0 [&>section]:border-0 [&>section]:pt-0">
                <BillableOrders orders={data.billable} canRaise={canCollect} onRaised={reload} />
              </div>
            )}
          </div>
          <NotificationsCard
            canRead={canReadNotes}
            notifications={data.notifications}
            onRead={reload}
          />
        </div>
      )}
    </div>
  );
}
