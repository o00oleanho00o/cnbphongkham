"use client";

// "Nhóm khách" of `/crm` (old CRM01 `segment` card): the five lifecycle stages and the at-risk cut, each with its
// number (`GET /api/v1/crm/segments`) and, when opened, the patients in it (`GET /api/v1/crm/segments/{key}/patients`,
// most overdue first). The marketing opt-out switch is the audited `PATCH /api/v1/patients/{id}` of Patient 360;
// staff without `patient.write` only see the state.
import Link from "next/link";
import { useCallback, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { EmptyRow, TableShell } from "@/components/admin/shared/ui-bits";
import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import {
  countsOf,
  defaultSegment,
  expectedVisitText,
  formatDay,
  SEGMENT_HINT,
  SEGMENT_LABEL,
  SEGMENT_ORDER,
  type SegmentKey,
  type SegmentPatient,
} from "@/lib/ops/crm-overview-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { cx } from "@/ui/classnames";

const PAGE_SIZE = 25;
const MAX_LIMIT = 200;

function SegmentList({ segmentKey, onChanged }: { segmentKey: SegmentKey; onChanged: () => void }) {
  const { can } = useSession();
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/crm/segments/{segment}/patients", {
          params: { path: { segment: segmentKey }, query: { limit } },
          signal,
        }),
      ),
    [segmentKey, limit],
  );
  const { data, error, loading, reload } = useLoad(load);
  const canSwitch = can("patient.write");

  async function switchOptOut(row: SegmentPatient) {
    const next = !row.marketing_opt_out;
    const ok = await confirm({
      title: next ? "Ghi nhận khách từ chối quảng bá?" : "Cho phép gửi quảng bá lại?",
      message: next
        ? `${row.full_name} sẽ không nhận tin kết nối lại hoặc quảng bá. Việc chăm sóc sau điều trị vẫn giữ.`
        : `${row.full_name} có thể nhận tin quảng bá và kết nối lại. Chỉ bật khi khách đã đồng ý.`,
      confirmLabel: next ? "Ghi nhận từ chối" : "Cho phép lại",
      tone: "normal",
    });
    if (!ok) return;
    setBusyId(row.patient_id);
    try {
      await unwrap(
        http.PATCH("/api/v1/patients/{patient_id}", {
          params: { path: { patient_id: row.patient_id } },
          body: { version: row.version, marketing_opt_out: next },
        }),
      );
      toast.push("success", next ? "Đã ghi nhận từ chối quảng bá." : "Đã cho phép quảng bá lại.");
    } catch (e) {
      toast.push(
        "error",
        e instanceof ApiError && e.code === "version_conflict"
          ? "Hồ sơ vừa được người khác sửa. Đã tải lại."
          : errorMessage(e),
      );
    } finally {
      setBusyId(null);
    }
    reload();
    onChanged();
  }

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={4} />;
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div>
      <TableShell
        headers={["Khách hàng", "Khám gần nhất", "Tái khám", "Còn buổi", "Phụ trách", "Quảng bá"]}
        minWidth={760}
      >
        {items.length === 0 ? (
          <EmptyRow colSpan={6} text="Chưa có khách trong nhóm này." />
        ) : (
          items.map((row) => (
            <tr key={row.patient_id} className="border-b border-line/60 last:border-0">
              <td className="px-4 py-3">
                <Link
                  href={`/patients/${row.patient_id}`}
                  className="font-semibold text-ink hover:text-brand-600 hover:underline"
                >
                  {row.full_name}
                </Link>
                <div className="text-label text-ink-soft">{row.patient_code}</div>
              </td>
              <td className="px-4 py-3 text-ink-soft">
                {row.last_visit_at ? formatDay(row.last_visit_at) : "Chưa có"}
              </td>
              <td className="px-4 py-3">
                <span className="text-ink">{expectedVisitText(row)}</span>
                {row.risk_level === "high" && (
                  <div className="mt-1">
                    <Badge tone="danger">Nguy cơ mất khách</Badge>
                  </div>
                )}
              </td>
              <td className="px-4 py-3 text-ink-soft">{row.remaining_sessions}</td>
              <td className="px-4 py-3 text-ink-soft">{row.cs_owner_name ?? "Chưa giao"}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={row.marketing_opt_out ? "warning" : "success"}>
                    {row.marketing_opt_out ? "Từ chối quảng bá" : "Có thể chăm sóc"}
                  </Badge>
                  {canSwitch && (
                    <Button
                      variant="quiet"
                      disabled={busyId === row.patient_id}
                      onClick={() => void switchOptOut(row)}
                    >
                      {row.marketing_opt_out ? "Cho phép lại" : "Ghi nhận từ chối"}
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))
        )}
      </TableShell>
      {total > items.length && (
        <div className="mt-3 flex flex-wrap items-center gap-3 text-small text-ink-soft">
          <span>
            Hiển thị {items.length}/{total}
          </span>
          {limit < MAX_LIMIT && (
            <Button
              variant="secondary"
              onClick={() => setLimit((n) => Math.min(n + PAGE_SIZE, MAX_LIMIT))}
            >
              Xem thêm
            </Button>
          )}
        </div>
      )}
      {confirmDialog}
    </div>
  );
}

export function SegmentsPanel() {
  const [chosen, setChosen] = useState<SegmentKey | null>(null);
  const load = useCallback(
    (signal: AbortSignal) => unwrap(http.GET("/api/v1/crm/segments", { signal })),
    [],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={3} />;
  if (!data) return null;

  const counts = countsOf(data.segments);
  const active = chosen ?? defaultSegment(counts);

  return (
    <div className="space-y-4">
      <p className="text-small text-ink-soft">
        {data.total_patients} hồ sơ · {data.marketing_opt_out} khách từ chối quảng bá
      </p>
      <div
        role="group"
        aria-label="Nhóm khách"
        className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6"
      >
        {SEGMENT_ORDER.map((key) => (
          <button
            key={key}
            type="button"
            aria-pressed={active === key}
            onClick={() => setChosen(key)}
            className={cx(
              "min-w-0 rounded-card border bg-surface p-4 text-left shadow-card transition-colors hover:bg-tile/50",
              active === key ? "border-brand-500 ring-2 ring-brand-100" : "border-line",
            )}
          >
            <span className="block truncate text-label text-ink-soft">{SEGMENT_LABEL[key]}</span>
            <span className="mt-1 block text-metric leading-tight font-bold text-heading">
              {counts[key]}
            </span>
            <span className="mt-1 block text-label text-ink-soft">{SEGMENT_HINT[key]}</span>
          </button>
        ))}
      </div>
      <Notice>
        Khách từ chối quảng bá không nhận tin kết nối lại hoặc quảng bá; sinh nhật không bao giờ tự
        động gửi. Việc chăm sóc sau điều trị vẫn theo kế hoạch của bác sĩ.
      </Notice>
      <section aria-label={SEGMENT_LABEL[active]}>
        <h3 className="mb-2 text-body-lg font-bold text-heading">{SEGMENT_LABEL[active]}</h3>
        <SegmentList key={active} segmentKey={active} onChanged={refresh} />
      </section>
    </div>
  );
}
