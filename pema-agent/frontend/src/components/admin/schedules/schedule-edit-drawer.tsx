// ported from: web/src/pages/schedule-edit-drawer.tsx
"use client";

// Deviations: typed client (`POST /admin/schedules`, `PATCH /admin/schedules/{job_id}`: the job id alone
// identifies the job, the original also sent account and thread); the schedule is the contract's
// `ScheduleInput` union and the time zone of the job travels with it.

import { useState } from "react";
import type { AccountInfo } from "@/lib/admin/shared/account-info";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type ScheduleKind = Schemas["ScheduleKind"];
type ScheduledJobItem = Schemas["ScheduledJob"];
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { ScheduleDestinationFields } from "@/components/admin/schedules/schedule-destination-fields";
import { ScheduleFieldsSection } from "@/components/admin/schedules/schedule-fields-section";
import {
  buildSchedule,
  initialOnce,
  scheduleChanged,
} from "@/lib/admin/schedules/schedule-form-helpers";

/**
 * Drawer tạo/sửa 1 lịch hẹn. `job=null` nghĩa là tạo mới - lúc đó mới cho
 * chọn account/thread/kind (xem `ScheduleDestinationFields` vì sao chỉ tạo
 * mới mới sửa được các ô này). Bố cục vay `account-edit-drawer.tsx`.
 */
export function ScheduleEditDrawer({
  job,
  accounts,
  timezone,
  onClose,
  onSaved,
}: {
  job: ScheduledJobItem | null;
  accounts: AccountInfo[];
  timezone: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const once = initialOnce(job, timezone);
  const [form, setForm] = useState({
    accountId: job?.account_id ?? accounts[0]?.id ?? "",
    threadId: job?.thread_id ?? "",
    threadType: job?.thread_type ?? 0,
    kind: job?.kind ?? "message",
    name: job?.name ?? "",
    payload: job?.payload ?? "",
    scheduleKind: (job?.schedule_kind ?? "once") as ScheduleKind,
    onceDate: once.date,
    onceTime: once.time,
    everyMinutes: job?.every_minutes ? String(job.every_minutes) : "60",
    cronExpr: job?.cron_expr ?? "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nen = useChotNen(onClose);

  async function save() {
    const schedule = buildSchedule(form);
    if (!schedule) {
      setError("Điền đủ thông tin lịch (ngày/giờ, số phút, hoặc biểu thức cron).");
      return;
    }
    if (!job && !form.threadId) {
      setError("Chọn cuộc trò chuyện để gửi lịch hẹn tới.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      if (job) {
        await unwrap(
          http.PATCH("/api/v1/admin/schedules/{job_id}", {
            params: { path: { job_id: job.id } },
            body: {
              name: form.name,
              payload: form.payload,
              schedule: scheduleChanged(job, once, form) ? schedule : undefined,
            },
          }),
        );
      } else {
        await unwrap(
          http.POST("/api/v1/admin/schedules", {
            body: {
              account_id: form.accountId,
              thread_id: form.threadId,
              thread_type: form.threadType,
              name: form.name,
              kind: form.kind as "message" | "agent",
              payload: form.payload,
              schedule,
              timezone,
            },
          }),
        );
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/25 backdrop-blur-[2px]" {...nen}>
      <div className="flex h-full w-full max-w-md flex-col border-l border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="font-semibold text-ink">{job ? `Sửa: ${job.name}` : "Thêm lịch hẹn"}</div>
          <button
            onClick={onClose}
            className="rounded-control border border-line px-3 py-1 text-small text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {!job && (
            <ScheduleDestinationFields
              accounts={accounts}
              accountId={form.accountId}
              threadId={form.threadId}
              kind={form.kind}
              onChange={(patch) => setForm({ ...form, ...patch })}
            />
          )}

          <div>
            <label htmlFor="sch-name" className="mb-1.5 block text-small font-medium text-ink">
              Tên
            </label>
            <input
              id="sch-name"
              className="gc-input w-full"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="vd: Nhắc họp 15h"
            />
          </div>

          <div>
            <label htmlFor="sch-payload" className="mb-1.5 block text-small font-medium text-ink">
              {form.kind === "agent" ? "Prompt cho agent" : "Nội dung gửi"}
            </label>
            <textarea
              id="sch-payload"
              className="gc-input min-h-28 w-full resize-y leading-relaxed"
              value={form.payload}
              onChange={(e) => setForm({ ...form, payload: e.target.value })}
              placeholder={
                form.kind === "agent"
                  ? "vd: Tóm tắt tin công nghệ nổi bật hôm nay"
                  : "vd: Nhớ họp với anh Nam lúc 3h chiều nhé"
              }
            />
          </div>

          <ScheduleFieldsSection
            job={job}
            timezone={timezone}
            scheduleKind={form.scheduleKind}
            onceDate={form.onceDate}
            onceTime={form.onceTime}
            everyMinutes={form.everyMinutes}
            cronExpr={form.cronExpr}
            onChange={(patch) => setForm({ ...form, ...patch })}
          />

          {error && <p className="text-small text-danger">{error}</p>}
        </div>

        <div className="border-t border-line px-5 py-4">
          <button
            onClick={save}
            disabled={busy || !form.name || !form.payload}
            className="w-full rounded-control bg-brand-500 py-2.5 text-body font-medium text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {busy ? "Đang lưu..." : job ? "Lưu thay đổi" : "Tạo lịch hẹn"}
          </button>
        </div>
      </div>
    </div>
  );
}
