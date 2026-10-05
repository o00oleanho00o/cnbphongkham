"use client";

// Contact form of "Việc hôm nay": which channel, what happened, what is next. Web prototype source:
// prototype/shared/crm-ui.js (modal "Chăm sóc · ...") with the same fields and rules. It only RECORDS a
// contact the person already made; nothing is sent from here (no auto-send, a human does the contact).
import { useMemo, useRef, useState, type FormEvent } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { AssigneeStatus } from "@/components/ops/assignee-status";
import { FilterChip, Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, newIdempotencyKey, unwrap } from "@/lib/api/client";
import { OWNER_ME, ownerIdFor, ownerOptions } from "@/lib/ops/assignee-options";
import {
  channelOfTask,
  defaultNoteFor,
  outcomeNeedsNextAction,
  validateResolve,
  type ResolveForm,
} from "@/lib/ops/crm-task-view";
import { localInputToIso } from "@/lib/ops/format";
import { CHANNEL_LABEL, OUTCOME_LABEL, PRIORITY_LABEL, RULE_LABEL } from "@/lib/ops/labels";
import { useSession } from "@/lib/session/session-context";
import { useAssignableStaff } from "@/lib/staff/use-assignable-staff";

type CrmTask = Schemas["CrmTaskOut"];
type CrmChannel = Schemas["CrmChannel"];
type CrmOutcome = Schemas["CrmOutcome"];

const CHANNELS: CrmChannel[] = ["call", "zalo", "sms", "internal_note"];

const OUTCOME_OPTIONS: SelectOption[] = (Object.keys(OUTCOME_LABEL) as CrmOutcome[]).map(
  (value) => ({
    value,
    label: OUTCOME_LABEL[value],
  }),
);

const PRIORITY_OPTIONS: SelectOption[] = (
  Object.keys(PRIORITY_LABEL) as Schemas["TaskPriority"][]
).map((value) => ({ value, label: PRIORITY_LABEL[value] }));

const DURATION_OPTIONS: SelectOption[] = [30, 45, 60, 90].map((m) => ({
  value: String(m),
  label: `${m} phút`,
}));

export function ResolveTaskSheet({
  task,
  patientName,
  presetFromShortcut,
  onClose,
  onDone,
}: {
  task: CrmTask;
  patientName: string;
  /** Opened from "Đánh dấu đã làm": channel and note are pre-filled from the task. */
  presetFromShortcut: boolean;
  onClose: () => void;
  /** Called with the updated task after the BE accepted the contact. */
  onDone: (updated: CrmTask) => void;
}) {
  const { user } = useSession();
  const toast = useToast();
  const idempotencyKey = useRef(newIdempotencyKey());
  const taskChannel = channelOfTask(task);
  const startChannel: CrmChannel = presetFromShortcut ? taskChannel : "call";

  const [form, setForm] = useState<ResolveForm>({
    channel: startChannel,
    outcome: "",
    note: presetFromShortcut ? defaultNoteFor(startChannel) : "",
    nextAction: "",
    hasBooking: false,
    bookingStart: "",
  });
  const [durationMin, setDurationMin] = useState("45");
  const {
    staff,
    loading: staffLoading,
    error: staffError,
    reload: reloadStaff,
  } = useAssignableStaff();
  // "me" (default), "keep" (the current owner stays) or the id of a colleague from `staff/assignable`.
  const [ownerValue, setOwnerValue] = useState(OWNER_ME);
  const [priority, setPriority] = useState<string>(task.priority);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const patch = (change: Partial<ResolveForm>) => setForm((f) => ({ ...f, ...change }));

  const ownerChoices = useMemo<SelectOption[]>(
    () =>
      ownerOptions({
        me: user,
        currentId: task.owner_user_id,
        currentName: task.owner_name,
        staff,
      }),
    [user, task.owner_user_id, task.owner_name, staff],
  );

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem = validateResolve(form);
    if (problem || !form.outcome) {
      setError(problem ?? "Chọn kết quả liên hệ.");
      return;
    }
    setBusy(true);
    setError("");
    const owner = ownerIdFor(ownerValue, user, task.owner_user_id) ?? user.id;
    const booking =
      form.outcome === "booked"
        ? {
            patient_id: task.patient_id,
            starts_at: localInputToIso(form.bookingStart),
            duration_min: Number(durationMin),
            crm_task_id: task.id,
          }
        : undefined;
    try {
      const updated = await unwrap(
        http.POST("/api/v1/crm/tasks/{task_id}/resolve", {
          params: {
            path: { task_id: task.id },
            header: { "Idempotency-Key": idempotencyKey.current },
          },
          body: {
            channel: form.channel,
            outcome: form.outcome,
            note: form.note.trim(),
            next_action_at: form.nextAction ? localInputToIso(form.nextAction) : null,
            owner_user_id: owner,
            priority: priority as Schemas["TaskPriority"],
            booking,
            version: task.version,
          },
        }),
      );
      toast.push("success", "Đã ghi nhận kết quả chăm sóc.");
      onDone(updated);
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "version_conflict"
          ? "Việc này vừa được người khác cập nhật. Đóng form để tải lại danh sách."
          : errorMessage(err),
      );
    } finally {
      setBusy(false);
    }
  }

  const needsNext = outcomeNeedsNextAction(form.outcome);

  return (
    <Sheet
      title={`Chăm sóc · ${patientName}`}
      subtitle={`${RULE_LABEL[task.rule_key]} · ${task.reason}`}
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="resolve-form" disabled={busy}>
            {busy ? "Đang lưu..." : "Lưu kết quả chăm sóc"}
          </PrimaryButton>
        </>
      }
    >
      <form id="resolve-form" onSubmit={(e) => void submit(e)} className="space-y-4">
        <Notice>
          Chỉ ghi nhận kết quả bạn đã liên hệ. Hệ thống không tự gửi Zalo, SMS hoặc gọi điện từ màn
          này.
        </Notice>

        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium text-ink">Kênh liên hệ</legend>
          <div className="flex flex-wrap gap-2">
            {CHANNELS.map((channel) => (
              <FilterChip
                key={channel}
                selected={form.channel === channel}
                onClick={() => patch({ channel })}
              >
                {CHANNEL_LABEL[channel]}
              </FilterChip>
            ))}
          </div>
        </fieldset>

        <Field label="Kết quả" htmlFor="resolve-outcome">
          <SelectMenu
            id="resolve-outcome"
            size="md"
            value={form.outcome}
            placeholder="Chọn kết quả liên hệ"
            options={OUTCOME_OPTIONS}
            onChange={(value) => patch({ outcome: value as CrmOutcome })}
          />
        </Field>

        <Field label="Nội dung / kết quả trao đổi" htmlFor="resolve-note">
          <textarea
            id="resolve-note"
            value={form.note}
            onChange={(e) => patch({ note: e.target.value })}
            rows={3}
            required
            placeholder="Ghi cụ thể kết quả và điều đã thống nhất với khách..."
            className="gc-input w-full"
          />
        </Field>

        {form.outcome === "booked" && (
          <div className="grid gap-3 rounded-xl border border-line bg-tile/40 p-3 sm:grid-cols-2">
            <Field label="Ngày giờ lịch hẹn" htmlFor="resolve-booking">
              <input
                id="resolve-booking"
                type="datetime-local"
                value={form.bookingStart}
                onChange={(e) => patch({ bookingStart: e.target.value, hasBooking: true })}
                className="gc-input w-full"
              />
            </Field>
            <Field label="Thời lượng" htmlFor="resolve-duration">
              <SelectMenu
                id="resolve-duration"
                size="md"
                value={durationMin}
                options={DURATION_OPTIONS}
                onChange={setDurationMin}
              />
            </Field>
            <p className="text-[12px] text-ink-soft sm:col-span-2">
              Lịch được lưu cùng lúc với việc chăm sóc; máy chủ kiểm tra trùng giờ bác sĩ trước khi
              hoàn tất.
            </p>
          </div>
        )}

        <Field
          label={needsNext ? "Ngày giờ gọi lại (bắt buộc)" : "Ngày giờ tiếp theo (nếu cần)"}
          htmlFor="resolve-next"
        >
          <input
            id="resolve-next"
            type="datetime-local"
            value={form.nextAction}
            onChange={(e) => patch({ nextAction: e.target.value })}
            className="gc-input w-full"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Phụ trách" htmlFor="resolve-owner">
            <SelectMenu
              id="resolve-owner"
              size="md"
              value={ownerValue}
              options={ownerChoices}
              onChange={setOwnerValue}
            />
            <AssigneeStatus loading={staffLoading} error={staffError} onRetry={reloadStaff} />
          </Field>
          <Field label="Ưu tiên" htmlFor="resolve-priority">
            <SelectMenu
              id="resolve-priority"
              size="md"
              value={priority}
              options={PRIORITY_OPTIONS}
              onChange={setPriority}
            />
          </Field>
        </div>

        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}
