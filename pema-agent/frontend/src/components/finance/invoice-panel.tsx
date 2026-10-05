"use client";

// "Hóa đơn & thanh toán" of the cashier (old web: `operations-ui.js` `cashier()`): the invoices with the filters
// "Tất cả", "Còn phải thu" and "Đã thanh toán", 12 per page, "Thu tiền" on an invoice with a balance (the dialog
// `PaymentDialog`), and under the table the quick orders that have no invoice yet ("Lập hóa đơn"). Money is the
// finance step's (U6): the BE says who may list (`finance.read` or `finance.collect`) and who may collect
// (`finance.collect`). A role with neither is told who handles invoices.
import Link from "next/link";
import { useCallback, useState } from "react";

import { BillableOrders } from "@/components/finance/billable-orders";
import { PaymentDialog } from "@/components/finance/payment-dialog";
import { ChipRow, FilterChip, ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  INVOICE_FILTERS,
  NO_INVOICES,
  formatVnd,
  invoiceKind,
  invoiceLine,
  invoiceTotals,
  matchesFilter,
  type BillableOrder,
  type InvoiceFilter,
  type InvoiceRow,
} from "@/lib/finance/finance-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button, buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { EmptyRow, TableShell } from "@/ui/table-shell";

const PAGE_SIZE = 12;
const FETCH_LIMIT = 200;
const HEADERS = [
  "Hóa đơn / bệnh nhân",
  "Dịch vụ / đơn nhanh",
  "Tổng tiền",
  "Đã thu",
  "Còn lại",
  "",
];

type PanelData = { invoices: InvoiceRow[]; total: number; billable: BillableOrder[] };

function Totals({ invoices, total }: { invoices: readonly InvoiceRow[]; total: number }) {
  const totals = invoiceTotals(invoices);
  return (
    <dl className="mb-3 flex flex-wrap gap-x-6 gap-y-1 text-small text-ink-soft">
      <div className="flex gap-1.5">
        <dt>Tổng hóa đơn</dt>
        <dd className="font-semibold text-ink">{total}</dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Đã thu</dt>
        <dd className="font-semibold text-ink tabular-nums">{formatVnd(totals.received)}</dd>
      </div>
      <div className="flex gap-1.5">
        <dt>Còn phải thu</dt>
        <dd className="font-semibold text-ink tabular-nums">{formatVnd(totals.due)}</dd>
      </div>
      {total > invoices.length && (
        <span className="text-label">(tính trên {invoices.length} hóa đơn gần nhất)</span>
      )}
    </dl>
  );
}

function InvoiceRows({
  rows,
  canCollect,
  onPay,
}: {
  rows: readonly InvoiceRow[];
  canCollect: boolean;
  onPay: (invoice: InvoiceRow) => void;
}) {
  return (
    <TableShell headers={HEADERS} minWidth={760}>
      {rows.length === 0 && <EmptyRow colSpan={HEADERS.length} text={NO_INVOICES} />}
      {rows.map((invoice) => (
        <tr key={invoice.id} className="border-b border-line align-top last:border-0">
          <td className="px-4 py-3">
            <div className="text-body font-semibold text-ink">{invoice.patient_name}</div>
            <div className="text-small text-ink-soft">{invoiceLine(invoice)}</div>
          </td>
          <td className="px-4 py-3 text-body text-ink">
            {invoiceKind(invoice)}
            {invoice.order_id !== null && (
              <Link
                href={`/orders/${invoice.order_id}`}
                className={buttonClass("quiet", "ml-2 min-h-0")}
                aria-label={`In tách đơn của ${invoice.patient_name}`}
              >
                In tách đơn
              </Link>
            )}
          </td>
          <td className="px-4 py-3 text-body text-ink tabular-nums">
            {formatVnd(invoice.amount_vnd)}
          </td>
          <td className="px-4 py-3 text-body text-ink tabular-nums">
            {formatVnd(invoice.received_vnd)}
          </td>
          <td className="px-4 py-3 text-body text-ink tabular-nums">
            {formatVnd(invoice.due_vnd)}
          </td>
          <td className="px-4 py-3">
            {invoice.due_vnd > 0 && canCollect ? (
              <Button
                onClick={() => onPay(invoice)}
                aria-label={`Thu tiền ${invoice.patient_name}`}
              >
                Thu tiền
              </Button>
            ) : (
              invoice.due_vnd <= 0 && <Badge tone="success">Đã thanh toán</Badge>
            )}
          </td>
        </tr>
      ))}
    </TableShell>
  );
}

export function InvoicePanel({ onChanged }: { onChanged: () => void }) {
  const toast = useToast();
  const { can } = useSession();
  const canCollect = can("finance.collect");
  const canList = canCollect || can("finance.read");
  const [filter, setFilter] = useState<InvoiceFilter>("all");
  const [page, setPage] = useState(0);
  const [paying, setPaying] = useState<InvoiceRow | null>(null);

  const load = useCallback(
    async (signal: AbortSignal): Promise<PanelData> => {
      if (!canList) return { invoices: [], total: 0, billable: [] };
      const [list, billable] = await Promise.all([
        unwrap(
          http.GET("/api/v1/finance/invoices", {
            params: { query: { limit: FETCH_LIMIT } },
            signal,
          }),
        ),
        unwrap(http.GET("/api/v1/finance/billable-orders", { signal })),
      ]);
      return { invoices: list.items, total: list.total, billable };
    },
    [canList],
  );
  const { data, error, loading, reload } = useLoad(load);

  if (!canList) {
    return (
      <Card title="Hóa đơn & thanh toán">
        <Notice>
          Hóa đơn và thu tiền do lễ tân, kế toán hoặc chủ phòng khám phụ trách. Đơn đã duyệt là căn
          cứ để lập hóa đơn; duyệt đơn không có nghĩa là đã cấp thuốc.
        </Notice>
      </Card>
    );
  }

  const shown = data ? data.invoices.filter((invoice) => matchesFilter(invoice, filter)) : [];
  const pages = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const rows = shown.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  function chooseFilter(next: InvoiceFilter) {
    setFilter(next);
    setPage(0);
  }

  function changed() {
    reload();
    onChanged();
  }

  return (
    <Card
      title="Hóa đơn & thanh toán"
      aside={
        <ChipRow label="Lọc hóa đơn">
          {INVOICE_FILTERS.map((option) => (
            <FilterChip
              key={option.id}
              selected={filter === option.id}
              onClick={() => chooseFilter(option.id)}
            >
              {option.label}
            </FilterChip>
          ))}
        </ChipRow>
      }
    >
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={2} />}
      {data && (
        <>
          <Totals invoices={data.invoices} total={data.total} />
          <InvoiceRows rows={rows} canCollect={canCollect} onPay={setPaying} />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-small text-ink-soft">
              {shown.length} hóa đơn · Trang {page + 1}/{pages}
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
          <BillableOrders orders={data.billable} canRaise={canCollect} onRaised={changed} />
        </>
      )}
      {paying !== null && (
        <PaymentDialog
          invoice={paying}
          onClose={() => setPaying(null)}
          onPaid={() => {
            setPaying(null);
            toast.push("success", "Đã ghi phiếu thu và cập nhật hóa đơn");
            changed();
          }}
        />
      )}
    </Card>
  );
}
