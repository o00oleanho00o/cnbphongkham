"use client";

// The five dialogs of the shared Inbox (frames WM17-WM23): Nhận, Tiếp quản (a reason is required and only staff
// see it), Trả lại (to the queue, or to the care agent when the patient is in the staff state), Giao cho... (owner
// and manager) and the history. The BE decides every rule (lock, role, limits, the 501 of the care loop until
// package M7): a dialog sends the request, shows the BE's answer and hands the updated conversation back.
import { useCallback, useMemo, useState } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { Notice, RetryNotice, ListSkeleton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, http, unwrap } from "@/lib/api/client";
import { assignmentErrorText, isThreadLocked } from "@/lib/ops/assignment-errors";
import { formatDateTime } from "@/lib/ops/format";
import { assignmentTitle, conversationCode } from "@/lib/ops/inbox-view";
import { shortName } from "@/lib/ops/presence-view";
import { ROLE_LABEL } from "@/lib/session/session-context";
import { useAssignableStaff } from "@/lib/staff/use-assignable-staff";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Conversation = Schemas["ConversationOut"];

export const REASON_MAX = 500;
export const NO_CARE_LOOP_TEXT = "Chưa nối với trợ lý chăm sóc nên chưa trả lại cho trợ lý được.";
const UNASSIGN = "none";

type DialogProps = {
  conversation: Conversation;
  /** Name of the identity the thread runs on ("Long"), or null when it cannot be told. */
  identityLabel: string | null;
  onClose: () => void;
  /** The BE's updated conversation; null when the thread must simply be reloaded (somebody got there first). */
  onDone: (updated: Conversation | null) => void;
};

const subtitleOf = (c: Conversation, identityLabel: string | null): string =>
  identityLabel ? `${conversationCode(c.id)} · ${identityLabel}` : conversationCode(c.id);

/** Runs one request, keeps the dialog open with the error on failure, and reports a lost race. */
function useAction(props: Pick<DialogProps, "onDone">) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { onDone } = props;

  const run = useCallback(
    async (request: () => Promise<Conversation>, onFail?: (e: unknown) => string | null) => {
      setBusy(true);
      setError("");
      try {
        onDone(await request());
      } catch (e) {
        if (isThreadLocked(e)) {
          toast.push("error", assignmentErrorText(e));
          onDone(null);
          return;
        }
        setError(onFail?.(e) ?? assignmentErrorText(e));
      } finally {
        setBusy(false);
      }
    },
    [onDone, toast],
  );
  return { busy, error, run };
}

export function ClaimDialog({ conversation, identityLabel, onClose, onDone }: DialogProps) {
  const { busy, error, run } = useAction({ onDone });
  const through = identityLabel ? ` "${identityLabel}"` : "";
  const submit = () =>
    run(() =>
      unwrap(
        http.POST("/api/v1/conversations/{conversation_id}/claim", {
          params: { path: { conversation_id: conversation.id } },
          body: { assignment_version: conversation.assignment_version },
        }),
      ),
    );
  return (
    <Dialog
      title="Nhận hội thoại này?"
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy} onClick={() => void submit()}>
            Nhận
          </Button>
        </>
      }
    >
      <p className="text-body text-ink">
        Bạn sẽ là người phụ trách và là người duy nhất nhắn khách qua
        {through || " danh tính của hội thoại"} cho đến khi trả lại hoặc có người tiếp quản. Cả đội
        thấy trên nhóm Zalo.
      </p>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Dialog>
  );
}

export function TakeoverDialog({
  conversation,
  onClose,
  onDone,
}: Omit<DialogProps, "identityLabel">) {
  const { busy, error, run } = useAction({ onDone });
  const [reason, setReason] = useState("");
  const [touched, setTouched] = useState(false);
  const empty = reason.trim() === "";
  const holder = conversation.assigned_user_name ?? "Đồng nghiệp";
  const submit = () =>
    run(() =>
      unwrap(
        http.POST("/api/v1/conversations/{conversation_id}/takeover", {
          params: { path: { conversation_id: conversation.id } },
          body: { reason: reason.trim(), assignment_version: conversation.assignment_version },
        }),
      ),
    );
  return (
    <Dialog
      title="Tiếp quản hội thoại"
      subtitle={`${holder} đang phụ trách hội thoại ${conversationCode(conversation.id)}.`}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy || empty} onClick={() => void submit()}>
            Tiếp quản
          </Button>
        </>
      }
    >
      <Field
        label="Lý do tiếp quản"
        hint="Chỉ nhân viên xem được lý do; khách không thấy. Tối đa 500 ký tự."
        error={touched && empty ? "Hãy nhập lý do tiếp quản." : undefined}
        required
      >
        {(control) => (
          <textarea
            {...control}
            value={reason}
            maxLength={REASON_MAX}
            rows={4}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => setTouched(true)}
            className={`${FIELD_CONTROL_CLASS} resize-y`}
          />
        )}
      </Field>
      <Notice tone="info">{shortName(holder)}, bạn và nhóm Zalo của đội sẽ nhận thông báo.</Notice>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Dialog>
  );
}

type ReleaseTarget = "queue" | "agent";

const RELEASE_OPTIONS: { id: ReleaseTarget; title: string; hint: string }[] = [
  {
    id: "queue",
    title: "Về hàng chờ",
    hint: "ai cũng nhận được; hội thoại hiện ở tab Chờ nhận.",
  },
  {
    id: "agent",
    title: "Trả lại cho trợ lý AI",
    hint: "trợ lý tiếp tục phụ trách. Chỉ trả được khi bệnh nhân đang ở trạng thái nhân viên xử lý.",
  },
];

/** The care loop answers 501 until package M7: say so in words and keep the dialog open. */
function releaseError(e: unknown): string | null {
  return e instanceof ApiError && e.code === "not_implemented" ? NO_CARE_LOOP_TEXT : null;
}

export function ReleaseDialog({ conversation, identityLabel, onClose, onDone }: DialogProps) {
  const { busy, error, run } = useAction({ onDone });
  const [target, setTarget] = useState<ReleaseTarget>("queue");
  const [note, setNote] = useState("");
  const submit = () =>
    run(
      () =>
        unwrap(
          http.POST("/api/v1/conversations/{conversation_id}/release", {
            params: { path: { conversation_id: conversation.id } },
            body: {
              to_agent: target === "agent",
              note: note.trim() || null,
              assignment_version: conversation.assignment_version,
            },
          }),
        ),
      releaseError,
    );
  return (
    <Dialog
      title="Trả lại hội thoại"
      subtitle={subtitleOf(conversation, identityLabel)}
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy} onClick={() => void submit()}>
            Trả lại
          </Button>
        </>
      }
    >
      <fieldset className="mb-3.5">
        <legend className="mb-1.5 text-label font-semibold text-ink-soft">Trả lại cho</legend>
        <div className="space-y-2">
          {RELEASE_OPTIONS.map((option) => (
            <label
              key={option.id}
              className="flex cursor-pointer items-start gap-2.5 rounded-tile border border-line px-3 py-2.5 text-body text-ink has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50"
            >
              <input
                type="radio"
                name="release-target"
                checked={target === option.id}
                onChange={() => setTarget(option.id)}
                className="mt-1"
              />
              <span>
                <span className="font-semibold">{option.title}</span> · {option.hint}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <Field
        label="Ghi chú bàn giao"
        hint="Trợ lý đọc ghi chú này ở các lượt sau. Thông tin cá nhân được che trước khi lưu. Tối đa 500 ký tự."
      >
        {(control) => (
          <textarea
            {...control}
            value={note}
            maxLength={REASON_MAX}
            rows={3}
            onChange={(e) => setNote(e.target.value)}
            className={`${FIELD_CONTROL_CLASS} resize-y`}
          />
        )}
      </Field>
      {error && <Notice tone={error === NO_CARE_LOOP_TEXT ? "warn" : "error"}>{error}</Notice>}
    </Dialog>
  );
}

export function AssignDialog({ conversation, identityLabel, onClose, onDone }: DialogProps) {
  const { busy, error, run } = useAction({ onDone });
  const { staff, loading, error: staffError, reload } = useAssignableStaff();
  const [picked, setPicked] = useState<string | null>(null);
  const holderId = conversation.assigned_user_id;
  const options = useMemo<SelectOption[]>(
    () => [
      ...staff.map((s) => ({ value: s.id, label: `${s.name} · ${ROLE_LABEL[s.role]}` })),
      { value: UNASSIGN, label: "Bỏ người phụ trách (về hàng chờ)" },
    ],
    [staff],
  );
  const fallback = staff.find((s) => s.id !== holderId)?.id ?? UNASSIGN;
  const value = picked ?? fallback;
  const submit = () =>
    run(() =>
      unwrap(
        http.POST("/api/v1/conversations/{conversation_id}/assign", {
          params: { path: { conversation_id: conversation.id } },
          body: {
            user_id: value === UNASSIGN ? null : value,
            assignment_version: conversation.assignment_version,
          },
        }),
      ),
    );
  return (
    <Dialog
      title="Giao hội thoại cho đồng nghiệp"
      subtitle={subtitleOf(conversation, identityLabel)}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy || loading} onClick={() => void submit()}>
            Giao
          </Button>
        </>
      }
    >
      <Field
        label="Người phụ trách"
        hint='Danh sách gồm chủ phòng khám, quản lý, bác sĩ và CSKH đang hoạt động. Chọn "Bỏ người phụ trách (về hàng chờ)" để ai cũng nhận được.'
      >
        {(control) => (
          <SelectMenu
            id={control.id}
            size="md"
            ariaLabel="Người phụ trách"
            value={value}
            options={options}
            onChange={setPicked}
          />
        )}
      </Field>
      {staffError && <RetryNotice message="Chưa tải được danh sách nhân viên." onRetry={reload} />}
      <Notice tone="info">
        Người đang giữ, người được giao và nhóm Zalo của đội sẽ nhận thông báo.
      </Notice>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Dialog>
  );
}

export function HistoryDialog({
  conversation,
  identityLabel,
  onClose,
}: Pick<DialogProps, "conversation" | "identityLabel" | "onClose">) {
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/conversations/{conversation_id}/assignments", {
          params: { path: { conversation_id: conversation.id } },
          signal,
        }),
      ),
    [conversation.id],
  );
  const { data, error, loading, reload } = useLoad(load);
  return (
    <Dialog
      title="Lịch sử phụ trách"
      subtitle={subtitleOf(conversation, identityLabel)}
      onClose={onClose}
      footer={
        <Button variant="secondary" onClick={onClose}>
          Đóng
        </Button>
      }
    >
      {error && !data && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data?.length === 0 && (
        <p className="text-body text-ink-soft">Hội thoại này chưa có ai nhận hay chuyển.</p>
      )}
      {data && data.length > 0 && (
        <ol aria-label="Lịch sử phụ trách" className="space-y-4">
          {data.map((event) => (
            <li key={event.id} className="border-l-2 border-line pl-3">
              <p className="text-label text-ink-soft">{formatDateTime(event.at)}</p>
              <p className="text-body font-semibold text-ink">{assignmentTitle(event)}</p>
              {event.reason && <p className="text-small text-ink-soft">Lý do: {event.reason}</p>}
              {event.by && <p className="text-label text-ink-soft">{event.by}</p>}
            </li>
          ))}
        </ol>
      )}
    </Dialog>
  );
}
