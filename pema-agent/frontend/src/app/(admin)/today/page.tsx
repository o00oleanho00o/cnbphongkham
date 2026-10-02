"use client";

// "Việc hôm nay": the CRM task queue of the day (`GET /api/v1/crm/tasks`, due by the end of today in
// clinic time). New screen (no zalo-agent original); behaviour from the web prototype's "CSKH hôm nay"
// (prototype/shared/crm-ui.js) and design-specs C1/C2/C6/I13. For tasks that staff send by hand it offers
// "Sao chép nội dung" and "Đánh dấu đã làm". The BE owns the rules; this page only lists and records.
// Several people work on the same queue: a `tasks.changed` event (GET /api/v1/events) reloads the list quietly,
// the open form and the filters stay as they are, and without the stream the list refreshes every 30 seconds.
import { useCallback, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { IconClipboardCheck } from "@/components/admin/shared/ops-icons";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { LiveStatus } from "@/components/ops/live-status";
import { ResolveTaskSheet } from "@/components/ops/today/resolve-task-sheet";
import { TaskCard } from "@/components/ops/today/task-card";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import type { LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import { type ChannelFilter, matchesChannel } from "@/lib/ops/crm-task-view";
import { copyText, messageToCopy } from "@/lib/ops/clipboard";
import { clinicDateKey, formatDate } from "@/lib/ops/format";
import { CHANNEL_LABEL, RULE_LABEL, TASK_STATUS_LABEL } from "@/lib/ops/labels";
import { displayName, usePatientIndex } from "@/lib/ops/use-patient-names";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

type CrmTask = Schemas["CrmTaskOut"];
type StatusFilter = "open" | "rescheduled" | "resolved";

const STATUSES: StatusFilter[] = ["open", "rescheduled", "resolved"];
const CHANNEL_FILTERS: ChannelFilter[] = ["all", "call", "zalo", "sms"];
const PAGE_SIZE = 200;
const LIVE_TYPES: readonly LiveEventType[] = ["tasks.changed"];

const RULE_OPTIONS: SelectOption[] = [
  { value: "", label: "Tất cả nhóm chăm sóc" },
  ...(Object.keys(RULE_LABEL) as Schemas["RuleKey"][]).map((value) => ({
    value,
    label: RULE_LABEL[value],
  })),
];

type Sheet = { task: CrmTask; shortcut: boolean };

export default function TodayPage() {
  const { user, can } = useSession();
  const toast = useToast();
  const patients = usePatientIndex();
  const [status, setStatus] = useState<StatusFilter>("open");
  const [channel, setChannel] = useState<ChannelFilter>("all");
  const [rule, setRule] = useState("");
  const [mineOnly, setMineOnly] = useState(false);
  const [sheet, setSheet] = useState<Sheet | null>(null);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/crm/tasks", {
          params: {
            query: {
              task_status: status,
              rule_key: rule ? (rule as Schemas["RuleKey"]) : undefined,
              owner_user_id: mineOnly ? user.id : undefined,
              // "Hôm nay" = everything due by the end of the clinic's day, overdue included. The API takes a
              // DATE (a datetime is a 422 "Dữ liệu gửi lên không hợp lệ") and reads it as that whole day.
              due_by: status === "resolved" ? undefined : clinicDateKey(),
              limit: PAGE_SIZE,
            },
          },
          signal,
        }),
      ),
    [status, rule, mineOnly, user.id],
  );
  const { data, error, loading, reload, refresh } = useLoad(load);
  const liveMode = useLiveEvents({ types: LIVE_TYPES, onEvent: refresh, onRefresh: refresh });

  const items = useMemo(() => data?.items ?? [], [data]);
  const visible = useMemo(() => items.filter((t) => matchesChannel(t, channel)), [items, channel]);
  const channelCounts = useMemo(
    () =>
      CHANNEL_FILTERS.map((c) => ({
        channel: c,
        count: items.filter((t) => matchesChannel(t, c)).length,
      })),
    [items],
  );

  const onCopy = useCallback(
    (task: CrmTask) => {
      void copyText(messageToCopy(task.suggested_action)).then((ok) =>
        toast.push(
          ok ? "success" : "error",
          ok ? "Đã sao chép nội dung." : "Không sao chép được, hãy chọn và sao chép thủ công.",
        ),
      );
    },
    [toast],
  );
  const onMarkDone = useCallback((task: CrmTask) => setSheet({ task, shortcut: true }), []);
  const onRecord = useCallback((task: CrmTask) => setSheet({ task, shortcut: false }), []);
  const closeSheet = useCallback(() => {
    setSheet(null);
    reload();
  }, [reload]);
  const onDone = useCallback(() => {
    setSheet(null);
    reload();
  }, [reload]);

  const canResolve = can("crm.task.resolve");

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        icon={IconClipboardCheck}
        title="Việc hôm nay"
        subtitle={`${formatDate(clinicDateKey())} · ${data ? `${data.total} việc` : "đang tải"}`}
      />

      <LiveStatus mode={liveMode} />

      <div className="mb-4 space-y-3">
        <ChipRow label="Trạng thái">
          {STATUSES.map((s) => (
            <FilterChip key={s} selected={status === s} onClick={() => setStatus(s)}>
              {TASK_STATUS_LABEL[s]}
            </FilterChip>
          ))}
        </ChipRow>
        <ChipRow label="Kênh liên hệ">
          {channelCounts.map(({ channel: c, count }) => (
            <FilterChip
              key={c}
              selected={channel === c}
              onClick={() => setChannel(c)}
              count={count}
            >
              {c === "all" ? "Mọi kênh" : CHANNEL_LABEL[c]}
            </FilterChip>
          ))}
        </ChipRow>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="sm:w-72">
            <SelectMenu
              size="md"
              ariaLabel="Nhóm chăm sóc"
              value={rule}
              options={RULE_OPTIONS}
              onChange={setRule}
            />
          </div>
          <FilterChip selected={mineOnly} onClick={() => setMineOnly((v) => !v)}>
            Việc của tôi
          </FilterChip>
        </div>
      </div>

      {error && <RetryNotice message={error} onRetry={reload} />}

      {loading && !data && <ListSkeleton />}

      {data && visible.length === 0 && !loading && (
        <EmptyState
          title={
            status === "open" ? "Hôm nay không còn việc cần làm" : "Không có việc nào ở mục này"
          }
          hint="Đổi bộ lọc trạng thái, kênh hoặc nhóm chăm sóc để xem các việc khác."
        />
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {visible.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            patientName={displayName(patients, task.patient_id, task.patient_code)}
            marketingOptOut={patients.get(task.patient_id)?.marketing_opt_out ?? false}
            onCopy={onCopy}
            canResolve={canResolve}
            onMarkDone={onMarkDone}
            onRecord={onRecord}
          />
        ))}
      </div>

      {sheet && (
        <ResolveTaskSheet
          task={sheet.task}
          patientName={displayName(patients, sheet.task.patient_id, sheet.task.patient_code)}
          presetFromShortcut={sheet.shortcut}
          onClose={closeSheet}
          onDone={onDone}
        />
      )}
    </div>
  );
}
