"use client";

// Xuất CSV: the commission table of the month as a file for Excel (old web: the button "Xuất CSV cho Excel" under
// the table, which saved `Pema-tien-thu-thuat-<tháng>.csv`). The month and the projection are the ones of the page
// header; a doctor exports only own rows. The file is UTF-8 with a byte order mark so Excel reads the accents, and a
// cell that could be read as a formula starts with an apostrophe. Any failure is "Không xuất được bảng".
import { useState } from "react";

import { useFinance } from "@/components/finance/finance-context";
import { Notice, PrimaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { downloadFinanceCsv } from "@/lib/finance/export-csv";
import { SCOPE_LABEL, csvFileName, financeErrorMessage } from "@/lib/finance/finance-view";
import { Card } from "@/ui/card";

export default function FinanceExportPage() {
  const { month, scope } = useFinance();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function download() {
    setProblem("");
    setBusy(true);
    try {
      await downloadFinanceCsv(month, scope);
      toast.push("success", `Đã tải ${csvFileName(month)}`);
    } catch (error) {
      setProblem(financeErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {problem !== "" && <Notice tone="error">{problem}</Notice>}
      <Card
        title="Xuất bảng tiền thủ thuật"
        subtitle="Một dòng cho mỗi người thực hiện của mỗi lượt, đúng bảng đang xem."
      >
        <dl className="grid grid-cols-1 gap-3 text-body sm:grid-cols-3">
          <div>
            <dt className="text-label text-ink-soft">Kỳ báo cáo</dt>
            <dd className="mt-0.5 font-semibold text-ink">{month}</dd>
          </div>
          <div>
            <dt className="text-label text-ink-soft">Phạm vi</dt>
            <dd className="mt-0.5 font-semibold text-ink">{SCOPE_LABEL[scope]}</dd>
          </div>
          <div>
            <dt className="text-label text-ink-soft">Tên tệp</dt>
            <dd className="mt-0.5 font-semibold break-all text-ink">{csvFileName(month)}</dd>
          </div>
        </dl>
        <p className="mt-3 text-small text-ink-soft">
          Đổi kỳ và phạm vi ở đầu trang. Tệp là CSV UTF-8 có dấu BOM nên Excel đọc đúng tiếng Việt.
        </p>
        <div className="mt-4">
          <PrimaryButton onClick={() => void download()} disabled={busy}>
            {busy ? "Đang tải..." : "Tải CSV cho Excel"}
          </PrimaryButton>
        </div>
      </Card>
    </div>
  );
}
