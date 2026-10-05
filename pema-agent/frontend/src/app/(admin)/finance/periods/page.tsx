"use client";

// Chốt kỳ: the "approve and close the month" workflow. The old web had two buttons under the table of a month;
// this screen lists the last twelve months with their state, how many entries each holds and how many still wait for
// approval, why an open month cannot be closed yet (the BE's sentence: only a month that ended, a month with data,
// no entry on the "Theo thực thu" basis that is not paid in full, nothing left pending) and the action that is next:
// "Chốt tháng" for an open month that can close, "Xác nhận đã chi" for a closed one. A paid month is final.
import Link from "next/link";
import { useCallback, useState } from "react";

import { useFinance } from "@/components/finance/finance-context";
import { ClosePeriodDialog, PayPeriodDialog } from "@/components/finance/finance-dialogs";
import { LoadState, StatusBadge } from "@/components/finance/finance-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import { financeHref, type PeriodRow } from "@/lib/finance/finance-view";
import { formatDate } from "@/lib/ops/format";
import { useLoad } from "@/lib/use-load";
import { Button, buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { EmptyRow, TableShell } from "@/ui/table-shell";

const HEADERS = ["Kỳ", "Trạng thái", "Số lượt", "Chờ duyệt", "Tình trạng", ""];

type Dialog = { kind: "close" | "pay"; month: string } | null;

/** What to tell about a month: why it cannot close, that it can, or when it was closed and paid. */
function stateLine(row: PeriodRow): string {
  if (row.status === "paid") {
    return `Đã chi ${formatDate(row.paid_at)} · Chứng từ ${row.reference ?? "-"}`;
  }
  if (row.status === "closed") return `Đã chốt ${formatDate(row.closed_at)}`;
  return row.blocker ?? "Sẵn sàng chốt";
}

export default function FinancePeriodsPage() {
  const { canWrite, scope, refreshKey, reload } = useFinance();
  const toast = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  const load = useCallback(
    (signal: AbortSignal) => {
      void refreshKey; // "Làm mới" and every change raise it: a new load function means "fetch again"
      return unwrap(http.GET("/api/v1/finance/periods", { signal }));
    },
    [refreshKey],
  );
  const { data, error, loading, reload: retry } = useLoad(load);

  function done() {
    setDialog(null);
    toast.push("success", "Đã ghi nhận thành công");
    reload();
  }

  return (
    <div className="space-y-4">
      <LoadState error={error} loading={loading} hasData={data !== undefined} onRetry={retry} />
      {data && (
        <Card
          title="Chốt kỳ"
          subtitle="12 tháng gần nhất. Chốt khóa các lượt của tháng; sau khi chốt không thêm, duyệt hay hủy lượt trong tháng đó."
        >
          <TableShell headers={HEADERS} minWidth={820}>
            {data.items.length === 0 && (
              <EmptyRow colSpan={HEADERS.length} text="Chưa có kỳ nào." />
            )}
            {data.items.map((row) => (
              <tr key={row.month} className="border-b border-line align-top last:border-0">
                <td className="px-4 py-3 text-body font-semibold text-ink">{row.month}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={row.status} />
                </td>
                <td className="px-4 py-3 text-body text-ink tabular-nums">{row.entry_count}</td>
                <td className="px-4 py-3 text-body text-ink tabular-nums">{row.pending_count}</td>
                <td className="max-w-md px-4 py-3 text-small text-ink-soft">{stateLine(row)}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={financeHref("/finance/entries", row.month, scope)}
                      className={buttonClass("secondary")}
                      aria-label={`Mở bảng tiền thủ thuật tháng ${row.month}`}
                    >
                      Mở bảng
                    </Link>
                    {canWrite && row.closable && (
                      <Button
                        onClick={() => setDialog({ kind: "close", month: row.month })}
                        aria-label={`Chốt tháng ${row.month}`}
                      >
                        Chốt tháng
                      </Button>
                    )}
                    {canWrite && row.status === "closed" && (
                      <Button
                        onClick={() => setDialog({ kind: "pay", month: row.month })}
                        aria-label={`Xác nhận đã chi tháng ${row.month}`}
                      >
                        Xác nhận đã chi
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </TableShell>
        </Card>
      )}
      {dialog?.kind === "close" && (
        <ClosePeriodDialog month={dialog.month} onClose={() => setDialog(null)} onDone={done} />
      )}
      {dialog?.kind === "pay" && (
        <PayPeriodDialog month={dialog.month} onClose={() => setDialog(null)} onDone={done} />
      )}
    </div>
  );
}
