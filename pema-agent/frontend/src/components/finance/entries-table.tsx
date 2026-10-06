"use client";

// "Bảng tiền thủ thuật": one row per performer of every procedure (old web: `finance.js` `table()`). Revenue is the
// performer's share of the net price; the fee is the base times the rate frozen on the entry. "Duyệt" and "Hủy"
// exist only while the month is open, for whoever may write, on a row that is not cancelled.
import { Button } from "@/ui/button";
import { EmptyRow, TableShell } from "@/ui/table-shell";
import { StatusBadge } from "@/components/finance/finance-ui";
import {
  BASIS_LABEL,
  NO_ENTRIES,
  baseLine,
  canAct,
  formatVnd,
  type FinancePeriod,
  type FinanceRow,
} from "@/lib/finance/finance-view";

const HEADERS = [
  "Ngày / Hồ sơ",
  "Thủ thuật / Bác sĩ",
  "Doanh số phân bổ",
  "Cơ sở × tỷ lệ",
  "Tiền thủ thuật",
  "Trạng thái",
];

export function EntriesTable({
  rows,
  period,
  canWrite,
  busyEntryId,
  onApprove,
  onVoid,
}: {
  rows: readonly FinanceRow[];
  period: FinancePeriod;
  canWrite: boolean;
  busyEntryId: string | null;
  onApprove: (row: FinanceRow) => void;
  onVoid: (row: FinanceRow) => void;
}) {
  return (
    <TableShell headers={HEADERS} minWidth={860}>
      {rows.length === 0 && <EmptyRow colSpan={HEADERS.length} text={NO_ENTRIES} />}
      {rows.map((row) => {
        const label = `${row.service_name} · ${row.patient_code} · ${row.doctor_name}`;
        const acts = canAct(period, canWrite, row.status);
        return (
          <tr
            key={`${row.entry_id}:${row.doctor_id}`}
            className="border-b border-line align-top last:border-0"
          >
            <td className="px-4 py-3">
              <div className="text-body text-ink">{row.date}</div>
              <div className="text-small text-ink-soft">{row.patient_code}</div>
            </td>
            <td className="px-4 py-3">
              <div className="text-body text-ink">{row.service_name}</div>
              <div className="text-small text-ink-soft">{row.doctor_name}</div>
            </td>
            <td className="px-4 py-3 text-body text-ink tabular-nums">
              {formatVnd(row.revenue_vnd)}
            </td>
            <td className="px-4 py-3">
              <div className="text-body text-ink tabular-nums">{baseLine(row)}</div>
              <div className="text-small text-ink-soft">{BASIS_LABEL[row.basis]}</div>
            </td>
            <td className="px-4 py-3 text-body font-bold text-heading tabular-nums">
              {formatVnd(row.fee_vnd)}
            </td>
            <td className="px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={row.status} />
                {acts && row.status === "pending" && (
                  <Button
                    variant="secondary"
                    disabled={busyEntryId === row.entry_id}
                    onClick={() => onApprove(row)}
                    aria-label={`Duyệt ${label}`}
                  >
                    Duyệt
                  </Button>
                )}
                {acts && (
                  <Button
                    variant="secondary"
                    disabled={busyEntryId === row.entry_id}
                    onClick={() => onVoid(row)}
                    aria-label={`Hủy ${label}`}
                  >
                    Hủy
                  </Button>
                )}
              </div>
              {row.status === "void" && row.note !== "" && (
                <div className="mt-1 text-label text-ink-soft">Lý do: {row.note}</div>
              )}
            </td>
          </tr>
        );
      })}
    </TableShell>
  );
}
