"use client";

// Patient page of a role that reads finance but has no Patient 360: the accountant ("Đối soát & thu ngân", old web
// `staff-context.js`: pages finance, cashier, patients, patient; capabilities billing and readFinance). It sees the
// header (name, code, age) and the tab "Dịch vụ & tài chính" (WC27) from `GET /patients/{id}/finance-tab`, which holds
// no clinical record. Tổng quan, Kế hoạch and Lịch sử of WC27 draw clinical data and stay out until a
// billing-only projection of them exists.
import { useCallback } from "react";

import { InitialAvatar } from "@/components/admin/shared/ui-bits";
import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { FinanceTab } from "@/components/ops/patient/finance-tab";
import { http, unwrap } from "@/lib/api/client";
import { ageYears } from "@/lib/ops/format";
import { GENDER_LABEL } from "@/lib/ops/labels";
import { useLoad } from "@/lib/use-load";

export function FinanceOnlyView({ patientId }: { patientId: string }) {
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/finance-tab", {
          params: { path: { patient_id: patientId } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);
  if (error !== "") return <RetryNotice message={error} onRetry={reload} />;
  if (loading && data === undefined) return <ListSkeleton rows={3} />;
  if (data === undefined) return null;
  const { patient } = data;
  const age = ageYears(patient.birth_date);
  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center gap-4 rounded-hero border border-brand-100 bg-brand-50 p-4 sm:p-5">
        <InitialAvatar name={patient.full_name} />
        <div className="min-w-0 flex-1 basis-48">
          <h1 className="text-title font-bold text-heading">{patient.full_name}</h1>
          <p className="text-small text-ink-soft">
            {patient.code} · {GENDER_LABEL[patient.gender ?? "unknown"]}
            {age !== null ? ` · ${age} tuổi` : ""}
            {patient.doctor_name ? ` · ${patient.doctor_name}` : ""}
          </p>
        </div>
      </header>
      <h2 className="text-section font-semibold text-heading">Dịch vụ &amp; tài chính</h2>
      <FinanceTab patient={patient} plans={data.plans} onChanged={refresh} />
    </div>
  );
}
