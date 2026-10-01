"use client";

// Hồ sơ bệnh nhân: search the patient list and open Patient 360 (read only). `GET /api/v1/patients?q=`.
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconSearch } from "@/components/admin/shared/dashboard-icons";
import { IconUser } from "@/components/admin/shared/ops-icons";
import { Badge, InitialAvatar } from "@/components/admin/shared/ui-bits";
import { EmptyState, ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { ageYears } from "@/lib/ops/format";
import { GENDER_LABEL } from "@/lib/ops/labels";
import { useLoad } from "@/lib/use-load";

const SEARCH_DEBOUNCE_MS = 300;
const PAGE_SIZE = 50;

export default function PatientsPage() {
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
          params: { query: { q: q || undefined, limit: PAGE_SIZE } },
          signal,
        }),
      ),
    [q],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        icon={IconUser}
        title="Hồ sơ bệnh nhân"
        subtitle="Tra cứu và xem Patient 360: lịch hẹn, liệu trình, chăm sóc và hội thoại"
      />

      <div className="relative mb-4 sm:max-w-md">
        <IconSearch
          size={15}
          className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-soft/60"
        />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Tìm bệnh nhân"
          placeholder="Tìm theo tên hoặc mã hồ sơ"
          className="gc-input w-full pl-9"
        />
      </div>

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={5} />}
      {data && items.length === 0 && (
        <EmptyState
          title="Không tìm thấy bệnh nhân"
          hint="Thử tên không dấu hoặc mã hồ sơ, ví dụ P003."
        />
      )}

      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {items.map((p) => {
          const age = ageYears(p.birth_date);
          return (
            <li key={p.id}>
              <Link
                href={`/patients/${p.id}`}
                className="gc-card flex min-h-[68px] items-center gap-3 px-3.5 py-3 hover:bg-tile/50"
              >
                <InitialAvatar name={p.full_name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-semibold text-ink">
                    {p.full_name}
                  </span>
                  <span className="block truncate text-[12px] text-ink-soft">
                    {p.code} · {GENDER_LABEL[p.gender ?? "unknown"]}
                    {age !== null ? ` · ${age} tuổi` : ""}
                    {p.doctor_name ? ` · ${p.doctor_name}` : ""}
                  </span>
                </span>
                {p.marketing_opt_out && (
                  <Badge tone="amber" dot={false}>
                    Từ chối quảng bá
                  </Badge>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
      {data && data.total > items.length && (
        <p className="mt-3 text-[13px] text-ink-soft">
          Hiển thị {items.length}/{data.total}. Gõ thêm để thu hẹp kết quả.
        </p>
      )}
    </div>
  );
}
