"use client";

// "Nhật ký chăm sóc" of `/crm` (old CRM01 `activity` card, "Kết quả chăm sóc đã ghi"): every contact the staff
// logged, newest first (`GET /api/v1/crm/activities`), with channel and outcome as `crm-ui.js` shows them. The
// chips narrow what is already on screen; nothing here sends a message or writes a record.
import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import {
  activityKindLabel,
  filterActivities,
  type ActivityFilter,
} from "@/lib/ops/crm-overview-view";
import { formatDateTime } from "@/lib/ops/format";
import { CHANNEL_LABEL, OUTCOME_LABEL } from "@/lib/ops/labels";
import { displayName, usePatientIndex } from "@/lib/ops/use-patient-names";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";

const PAGE_SIZE = 50;
const MAX_LIMIT = 200;

type Channel = Schemas["CrmChannel"];
type Outcome = Schemas["CrmOutcome"];

const CHANNELS = Object.keys(CHANNEL_LABEL) as Channel[];

const OUTCOME_OPTIONS: SelectOption[] = [
  { value: "all", label: "Mọi kết quả" },
  ...(Object.keys(OUTCOME_LABEL) as Outcome[]).map((value) => ({
    value,
    label: OUTCOME_LABEL[value],
  })),
];

export function ActivitiesPanel() {
  const patients = usePatientIndex();
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [filter, setFilter] = useState<ActivityFilter>({ channel: "all", outcome: "all" });

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(http.GET("/api/v1/crm/activities", { params: { query: { limit } }, signal })),
    [limit],
  );
  const { data, error, loading, reload } = useLoad(load);
  const shown = useMemo(() => filterActivities(data?.items ?? [], filter), [data, filter]);

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={4} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <ChipRow label="Kênh liên hệ">
          <FilterChip
            selected={filter.channel === "all"}
            onClick={() => setFilter({ ...filter, channel: "all" })}
          >
            Tất cả
          </FilterChip>
          {CHANNELS.map((channel) => (
            <FilterChip
              key={channel}
              selected={filter.channel === channel}
              onClick={() => setFilter({ ...filter, channel })}
            >
              {CHANNEL_LABEL[channel]}
            </FilterChip>
          ))}
        </ChipRow>
        <div className="sm:w-72">
          <SelectMenu
            size="md"
            ariaLabel="Kết quả liên hệ"
            value={filter.outcome}
            options={OUTCOME_OPTIONS}
            onChange={(value) =>
              setFilter({ ...filter, outcome: value === "all" ? "all" : (value as Outcome) })
            }
          />
        </div>
      </div>

      {shown.length === 0 ? (
        <EmptyState
          title="Chưa có kết quả chăm sóc nào"
          hint="Kết quả hiện ở đây sau khi nhân viên ghi nhận ở Việc hôm nay."
        />
      ) : (
        <ul className="space-y-3">
          {shown.map((activity) => (
            <li key={activity.id}>
              <Card padded={false} className="px-4 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <Link
                    href={`/patients/${activity.patient_id}`}
                    className="text-body font-semibold text-ink hover:text-brand-600 hover:underline"
                  >
                    {displayName(patients, activity.patient_id, null)}
                  </Link>
                  <span className="text-label text-ink-soft">
                    {formatDateTime(activity.occurred_at)}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  <Badge tone={activity.kind === "complaint" ? "danger" : "info"} dot={false}>
                    {activityKindLabel(activity.kind)}
                  </Badge>
                  <Badge tone="neutral" dot={false}>
                    {CHANNEL_LABEL[activity.channel]}
                  </Badge>
                  {activity.outcome && (
                    <Badge tone="brand" dot={false}>
                      {OUTCOME_LABEL[activity.outcome]}
                    </Badge>
                  )}
                </div>
                <p className="mt-2 text-body whitespace-pre-line text-ink">{activity.note}</p>
                <p className="mt-1.5 text-label text-ink-soft">
                  {activity.actor_name ?? "Hệ thống"}
                  {activity.next_action_at
                    ? ` · hẹn liên hệ lại ${formatDateTime(activity.next_action_at)}`
                    : ""}
                </p>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {data.total > data.items.length && limit < MAX_LIMIT && (
        <div className="flex flex-wrap items-center gap-3 text-small text-ink-soft">
          <span>
            Hiển thị {data.items.length}/{data.total}
          </span>
          <Button
            variant="secondary"
            onClick={() => setLimit((n) => Math.min(n + PAGE_SIZE, MAX_LIMIT))}
          >
            Xem thêm
          </Button>
        </div>
      )}
    </div>
  );
}
