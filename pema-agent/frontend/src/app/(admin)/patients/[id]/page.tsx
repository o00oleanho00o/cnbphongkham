"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { Suspense, useCallback } from "react";

import { IconChevronLeft } from "@/components/admin/shared/ops-icons";
import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { FinanceOnlyView } from "@/components/ops/patient/finance-only-view";
import { Patient360View } from "@/components/ops/patient/patient-360-view";
import { http, unwrap } from "@/lib/api/client";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

export default function Patient360Page() {
  const { id } = useParams<{ id: string }>();
  const { can } = useSession();
  const allowed = can("patient.read_360");
  // the accountant has no Patient 360: it gets the billing tab alone, from a projection without clinical data
  const financeOnly = !allowed && can("finance.read");

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/360", {
          params: { path: { patient_id: id } },
          signal,
        }),
      ),
    [id],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);

  return (
    <div>
      <Link
        href="/patients"
        className="mb-3 inline-flex min-h-11 items-center gap-1 text-body font-medium text-brand-500 hover:text-brand-600"
      >
        <IconChevronLeft size={18} />
        Danh sách hồ sơ
      </Link>
      {financeOnly && <FinanceOnlyView patientId={id} />}
      {!allowed && !financeOnly && (
        <p className="text-body text-ink-soft">Vai trò của bạn không được xem Patient 360.</p>
      )}
      {allowed && error && <RetryNotice message={error} onRetry={reload} />}
      {allowed && loading && !data && <ListSkeleton rows={3} />}
      {allowed && data && (
        <Suspense fallback={<ListSkeleton rows={3} />}>
          <Patient360View data={data} onChanged={refresh} />
        </Suspense>
      )}
    </div>
  );
}
