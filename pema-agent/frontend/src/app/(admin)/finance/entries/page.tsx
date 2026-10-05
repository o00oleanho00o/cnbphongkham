"use client";

// Tiền thủ thuật (old web: `finance.js` `work()`): the form that records a performed procedure, the table of the
// month with "Duyệt" and "Hủy" per row, "Xuất CSV cho Excel" and the two buttons that end a month, "Chốt tháng đã
// kết thúc" and "Xác nhận đã chi". A closed month is immutable: its table has no form and no row action. A doctor
// (and the owner on "Cá nhân") sees only own rows and nothing to change. `?form=open` opens the form.
import { useSearchParams } from "next/navigation";
import { useCallback, useState } from "react";

import { EntriesTable } from "@/components/finance/entries-table";
import { EntryFormPanel } from "@/components/finance/entry-form";
import { useFinance } from "@/components/finance/finance-context";
import {
  ClosePeriodDialog,
  PayPeriodDialog,
  VoidEntryDialog,
} from "@/components/finance/finance-dialogs";
import { LoadState, StatusBadge } from "@/components/finance/finance-ui";
import { Notice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import type { ServiceRow } from "@/lib/catalog/catalog-view";
import { downloadFinanceCsv } from "@/lib/finance/export-csv";
import {
  PERIOD_ACTION_LABEL,
  financeErrorMessage,
  periodAction,
  type FinanceEntries,
  type FinanceRow,
  type InvoiceRow,
} from "@/lib/finance/finance-view";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";

type EntriesData = {
  table: FinanceEntries;
  services: ServiceRow[];
  invoices: InvoiceRow[];
};

type Dialog = { kind: "void"; row: FinanceRow } | { kind: "close" } | { kind: "pay" } | null;

export default function FinanceEntriesPage() {
  const { month, scope, canWrite, refreshKey, reload } = useFinance();
  const toast = useToast();
  const params = useSearchParams();
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busyEntryId, setBusyEntryId] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  const load = useCallback(
    async (signal: AbortSignal): Promise<EntriesData> => {
      void refreshKey; // "Làm mới" and every change raise it: a new load function means "fetch again"
      const table = await unwrap(
        http.GET("/api/v1/finance/entries", { params: { query: { month, scope } }, signal }),
      );
      if (!table.can_write || table.period.status !== "open") {
        return { table, services: [], invoices: [] };
      }
      const [services, invoices] = await Promise.all([
        unwrap(http.GET("/api/v1/services", { params: { query: { active: true } }, signal })),
        unwrap(http.GET("/api/v1/finance/invoices", { params: { query: { limit: 200 } }, signal })),
      ]);
      return { table, services, invoices: invoices.items };
    },
    [month, scope, refreshKey],
  );
  const { data, error, loading, reload: retry } = useLoad(load);

  async function approve(row: FinanceRow) {
    setProblem("");
    setBusyEntryId(row.entry_id);
    try {
      await unwrap(
        http.POST("/api/v1/finance/entries/{entry_id}/approve", {
          params: { path: { entry_id: row.entry_id } },
        }),
      );
      toast.push("success", "Đã ghi nhận thành công");
      reload();
    } catch (err) {
      setProblem(financeErrorMessage(err));
    } finally {
      setBusyEntryId(null);
    }
  }

  async function exportCsv() {
    setProblem("");
    try {
      await downloadFinanceCsv(month, scope);
    } catch (err) {
      setProblem(financeErrorMessage(err));
    }
  }

  function done() {
    setDialog(null);
    toast.push("success", "Đã ghi nhận thành công");
    reload();
  }

  const table = data?.table;
  const action = table ? periodAction(table.period.status, canWrite && table.can_write) : null;
  return (
    <div className="space-y-4">
      <LoadState error={error} loading={loading} hasData={data !== undefined} onRetry={retry} />
      {problem !== "" && <Notice tone="error">{problem}</Notice>}
      {data && table && (
        <>
          {table.can_write && table.period.status === "open" && data.services.length > 0 && (
            <EntryFormPanel
              today={table.today}
              services={data.services}
              doctors={table.doctors}
              invoices={data.invoices}
              defaultOpen={params.get("form") === "open"}
              onSaved={reload}
            />
          )}
          <Card>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-body-lg font-bold text-heading">
                  Bảng tiền thủ thuật • {table.month}
                </h2>
                <StatusBadge status={table.period.status} />
              </div>
              <Button variant="secondary" onClick={() => void exportCsv()}>
                Xuất CSV cho Excel
              </Button>
            </div>
            <EntriesTable
              rows={table.rows}
              period={table.period}
              canWrite={table.can_write}
              busyEntryId={busyEntryId}
              onApprove={(row) => void approve(row)}
              onVoid={(row) => setDialog({ kind: "void", row })}
            />
            {action !== null && (
              <div className="mt-4 flex flex-wrap gap-3">
                <Button onClick={() => setDialog({ kind: action })}>
                  {PERIOD_ACTION_LABEL[action]}
                </Button>
              </div>
            )}
          </Card>
        </>
      )}
      {dialog?.kind === "void" && (
        <VoidEntryDialog
          entryId={dialog.row.entry_id}
          label={`${dialog.row.service_name} · ${dialog.row.patient_code}`}
          onClose={() => setDialog(null)}
          onDone={done}
        />
      )}
      {dialog?.kind === "close" && (
        <ClosePeriodDialog month={month} onClose={() => setDialog(null)} onDone={done} />
      )}
      {dialog?.kind === "pay" && (
        <PayPeriodDialog month={month} onClose={() => setDialog(null)} onDone={done} />
      )}
    </div>
  );
}
