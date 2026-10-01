"use client";

// Hàng đợi duyệt AI: every text the AI wants to send to a patient (patient_channel) waits here until a
// person approves it, plus red-flag alerts, patient photos flagged for staff and identity checks.
// `GET /api/v1/review-items`; detail on `?i=<id>` (child screen on a phone, side pane on desktop).
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { IconShieldCheck } from "@/components/admin/shared/ops-icons";
import { MasterDetail } from "@/components/ops/master-detail";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { ReviewDetail } from "@/components/ops/review/review-detail";
import { ReviewList } from "@/components/ops/review/review-list";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { REVIEW_KIND_LABEL, REVIEW_STATUS_LABEL } from "@/lib/ops/labels";
import { displayName, usePatientIndex } from "@/lib/ops/use-patient-names";
import { useLoad } from "@/lib/use-load";

type StatusTab = Extract<
  Schemas["ReviewStatus"],
  "pending" | "escalated" | "approved" | "rejected"
>;

const TABS: StatusTab[] = ["pending", "escalated", "approved", "rejected"];

const KIND_OPTIONS: SelectOption[] = [
  { value: "", label: "Mọi loại" },
  ...(Object.keys(REVIEW_KIND_LABEL) as Schemas["ReviewKind"][]).map((value) => ({
    value,
    label: REVIEW_KIND_LABEL[value],
  })),
];

function ReviewContent() {
  const router = useRouter();
  const params = useSearchParams();
  const selectedId = params.get("i");
  const patients = usePatientIndex();
  const [tab, setTab] = useState<StatusTab>("pending");
  const [kind, setKind] = useState("");
  const [doctorOnly, setDoctorOnly] = useState(false);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/review-items", {
          params: {
            query: {
              review_status: tab,
              kind: kind ? (kind as Schemas["ReviewKind"]) : undefined,
              requires_doctor: doctorOnly ? true : undefined,
              limit: 100,
            },
          },
          signal,
        }),
      ),
    [tab, kind, doctorOnly],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);

  const open = useCallback((id: string) => router.push(`/review?i=${id}`), [router]);
  const back = useCallback(() => router.push("/review"), [router]);
  const nameOf = useCallback(
    (item: Schemas["ReviewItemOut"]) => displayName(patients, item.patient_id, item.patient_code),
    [patients],
  );

  const selected = items.find((i) => i.id === selectedId);
  const selectedName = selected ? nameOf(selected) : "bệnh nhân";

  const list = (
    <div>
      <div className="mb-3 space-y-3">
        <ChipRow label="Trạng thái duyệt">
          {TABS.map((t) => (
            <FilterChip key={t} selected={tab === t} onClick={() => setTab(t)}>
              {REVIEW_STATUS_LABEL[t]}
            </FilterChip>
          ))}
        </ChipRow>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="sm:w-60">
            <SelectMenu
              size="md"
              ariaLabel="Loại mục duyệt"
              value={kind}
              options={KIND_OPTIONS}
              onChange={setKind}
            />
          </div>
          <FilterChip selected={doctorOnly} onClick={() => setDoctorOnly((v) => !v)}>
            Cần bác sĩ
          </FilterChip>
        </div>
      </div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={4} />}
      {data && items.length === 0 && (
        <EmptyState
          title={
            tab === "pending" ? "Không có nháp nào chờ duyệt" : "Không có mục nào ở trạng thái này"
          }
          hint="Khi trợ lý AI soạn tin cho khách, nháp và nguồn trích dẫn hiện ở đây."
        />
      )}
      <ReviewList items={items} selectedId={selectedId} nameOf={nameOf} onOpen={open} />
    </div>
  );

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        icon={IconShieldCheck}
        title="Hàng đợi duyệt AI"
        subtitle="Không tin nào của trợ lý AI tới khách khi chưa có người duyệt"
      />
      <MasterDetail
        list={list}
        detailOpen={selectedId !== null}
        onBack={back}
        backLabel="Danh sách chờ duyệt"
        detail={
          selectedId ? (
            <ReviewDetail
              key={selectedId}
              itemId={selectedId}
              patientName={selectedName}
              onChanged={reload}
            />
          ) : null
        }
        emptyDetail={
          <EmptyState
            title="Chọn một mục để xem"
            hint="Mỗi nháp kèm nguồn trích dẫn. Bạn có thể duyệt, sửa rồi duyệt, từ chối hoặc chuyển bác sĩ."
          />
        }
      />
    </div>
  );
}

export default function ReviewPage() {
  return (
    <Suspense fallback={<ListSkeleton rows={4} />}>
      <ReviewContent />
    </Suspense>
  );
}
