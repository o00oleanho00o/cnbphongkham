"use client";

// Ảnh trước / sau: the old web's `studio` screen. Choose a patient, then compare the photos of one view
// (`StudioView`). The patient and the view live in the address (`?patient=<id>&view=`) so a colleague can be sent
// the link. Who may open it is the BE's (`patient.read_360`; a doctor only at their own patients).
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconSearch } from "@/components/admin/shared/dashboard-icons";
import { InitialAvatar } from "@/components/admin/shared/ui-bits";
import { StudioView } from "@/components/catalog/studio-view";
import { EmptyState, ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

const SEARCH_DEBOUNCE_MS = 300;
const RESULT_LIMIT = 8;
const DEFAULT_VIEW = "Chính diện";

function PatientPicker({ onPick }: { onPick: (patientId: string) => void }) {
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQ(query.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients", {
          params: { query: { q: q || undefined, limit: RESULT_LIMIT } },
          signal,
        }),
      ),
    [q],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);

  return (
    <div>
      <div className="relative mb-3 sm:max-w-md">
        <IconSearch
          size={15}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-soft/60"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Tìm bệnh nhân"
          placeholder="Tìm theo tên hoặc mã hồ sơ"
          className={cx(FIELD_BASE_CLASS, "w-full pl-9")}
        />
      </div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data && items.length === 0 && (
        <EmptyState
          title="Không tìm thấy bệnh nhân"
          hint="Thử tên không dấu hoặc mã hồ sơ, ví dụ P003."
        />
      )}
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 wide:grid-cols-4">
        {items.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onPick(p.id)}
              className="flex min-h-[68px] w-full items-center gap-3 rounded-card border border-line bg-surface px-3.5 py-3 text-left shadow-card hover:bg-tile/50"
            >
              <InitialAvatar name={p.full_name} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-body font-semibold text-ink">
                  {p.full_name}
                </span>
                <span className="block truncate text-label text-ink-soft">{p.code}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StudioPage() {
  const { can } = useSession();
  const router = useRouter();
  const params = useSearchParams();
  const patientId = params.get("patient");
  const view = params.get("view") ?? DEFAULT_VIEW;

  const go = useCallback(
    (nextPatient: string | null, nextView: string) => {
      const next = new URLSearchParams();
      if (nextPatient) next.set("patient", nextPatient);
      if (nextPatient && nextView !== DEFAULT_VIEW) next.set("view", nextView);
      const search = next.toString();
      router.replace(search === "" ? "/studio" : `/studio?${search}`);
    },
    [router],
  );

  return (
    <div>
      <PageHeader
        title="Ảnh trước / sau"
        subtitle="Ảnh theo cùng góc và mốc điều trị giúp bác sĩ xem tiến triển trong ngữ cảnh."
      />
      {!can("patient.read_360") && (
        <EmptyState
          title="Bạn không có quyền xem ảnh bệnh nhân"
          hint="Mục này dành cho bác sĩ, chăm sóc khách hàng và quản lý."
        />
      )}
      {can("patient.read_360") && patientId === null && (
        <PatientPicker onPick={(id) => go(id, DEFAULT_VIEW)} />
      )}
      {can("patient.read_360") && patientId !== null && (
        <div className="space-y-3">
          <button
            type="button"
            onClick={() => go(null, DEFAULT_VIEW)}
            className="text-small font-medium text-link hover:underline"
          >
            ← Chọn bệnh nhân khác
          </button>
          <StudioView patientId={patientId} view={view} onView={(v) => go(patientId, v)} />
        </div>
      )}
    </div>
  );
}

export default function StudioRoute() {
  return (
    <Suspense fallback={<ListSkeleton rows={3} />}>
      <StudioPage />
    </Suspense>
  );
}
