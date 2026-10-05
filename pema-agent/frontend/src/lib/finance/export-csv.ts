// "Xuất CSV cho Excel": the file comes from `GET /api/v1/finance/export` (UTF-8 with a byte order mark, the
// caller's projection) and is saved through a blob, like the old page did, because a plain link could not carry the
// session error. Any failure is the old sentence "Không xuất được bảng".
import { EXPORT_FAILED, csvFileName, type FinanceScope } from "@/lib/finance/finance-view";

const REVOKE_DELAY_MS = 1000;

export async function downloadFinanceCsv(month: string, scope: FinanceScope): Promise<void> {
  const query = new URLSearchParams({ month, scope });
  const response = await fetch(`/api/v1/finance/export?${query.toString()}`, {
    credentials: "include",
  }).catch(() => null);
  if (response === null || !response.ok) throw new Error(EXPORT_FAILED);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = csvFileName(month);
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_DELAY_MS);
}
