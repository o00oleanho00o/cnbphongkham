"use client";

// Hồ sơ bệnh nhân: search the patient list, filter it with the four chips of the old web (Tất cả, Đang điều trị,
// Tái khám tuần này, Có cảnh báo; `?view=` of `GET /api/v1/patients`, so a page of 50 is a page of the chip),
// open Patient 360, and "＋ Hồ sơ mới" (with `patient.write`) which calls `POST /api/v1/patients`.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconSearch } from "@/components/admin/shared/dashboard-icons";
import { Badge, InitialAvatar } from "@/components/admin/shared/ui-bits";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { NewPatientDialog } from "@/components/ops/patient/new-patient-dialog";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import { ageYears } from "@/lib/ops/format";
import { GENDER_LABEL } from "@/lib/ops/labels";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

const SEARCH_DEBOUNCE_MS = 300;
const PAGE_SIZE = 50;

type View = "all" | "active" | "next" | "alerts";

const CHIPS: readonly { id: View; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "active", label: "Đang điều trị" },
  { id: "next", label: "Tái khám tuần này" },
  { id: "alerts", label: "Có cảnh báo" },
];

function emptyHint(view: View): string {
  if (view === "all") return "Thử tên không dấu hoặc mã hồ sơ, ví dụ P003.";
  return "Chọn “Tất cả” để bỏ bộ lọc.";
}

export default function PatientsPage() {
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  const [view, setView] = useState<View>("all");
  const [creating, setCreating] = useState(false);
  const router = useRouter();
  const toast = useToast();
  const { can } = useSession();

  useEffect(() => {
    const timer = setTimeout(() => setQ(query.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients", {
          params: { query: { q: q || undefined, view, limit: PAGE_SIZE } },
          signal,
        }),
      ),
    [q, view],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);

  return (
    <div>
      <PageHeader
        title="Hồ sơ bệnh nhân"
        subtitle="Tra cứu và xem Patient 360: lịch hẹn, liệu trình, chăm sóc và hội thoại"
        aside={
          can("patient.write") ? (
            <Button onClick={() => setCreating(true)}>＋ Hồ sơ mới</Button>
          ) : undefined
        }
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
          className={cx(FIELD_BASE_CLASS, "w-full pl-9")}
        />
      </div>

      <div className="mb-4">
        <ChipRow label="Lọc hồ sơ">
          {CHIPS.map((chip) => (
            <FilterChip key={chip.id} selected={view === chip.id} onClick={() => setView(chip.id)}>
              {chip.label}
            </FilterChip>
          ))}
        </ChipRow>
      </div>

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={5} />}
      {data && items.length === 0 && (
        <EmptyState title="Không tìm thấy bệnh nhân" hint={emptyHint(view)} />
      )}

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 wide:grid-cols-4">
        {items.map((p) => {
          const age = ageYears(p.birth_date);
          return (
            <li key={p.id}>
              <Link
                href={`/patients/${p.id}`}
                className="flex min-h-[68px] items-center gap-3 rounded-card border border-line bg-surface px-3.5 py-3 shadow-card hover:bg-tile/50"
              >
                <InitialAvatar name={p.full_name} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-body font-semibold text-ink">
                    {p.full_name}
                  </span>
                  <span className="block truncate text-label text-ink-soft">
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
        <p className="mt-3 text-small text-ink-soft">
          Hiển thị {items.length}/{data.total}. Gõ thêm để thu hẹp kết quả.
        </p>
      )}

      {creating && (
        <NewPatientDialog
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            toast.push("success", "Đã tạo hồ sơ");
            router.push(`/patients/${created.id}`);
          }}
        />
      )}
    </div>
  );
}
