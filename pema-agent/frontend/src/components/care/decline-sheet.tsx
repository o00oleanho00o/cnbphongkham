"use client";

// Decline a handoff: a reason (kept for the routing and for the skill profiles, never sent to the patient) and,
// optionally, a colleague who should take it. The colleague list is `GET /api/v1/staff/assignable`; the backend
// decides whether the suggestion is valid.
import { useMemo, useState } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { REASON_MAX, declineError } from "@/lib/care/forms";
import { ROLE_LABEL, useSession } from "@/lib/session/session-context";
import { useAssignableStaff } from "@/lib/staff/use-assignable-staff";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

const NOBODY = "";

export function DeclineSheet({
  patientName,
  busy,
  error,
  onClose,
  onSubmit,
}: {
  patientName: string;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (reason: string, suggestUserId: string | null) => void;
}) {
  const { user } = useSession();
  const { staff, loading, error: staffError, reload } = useAssignableStaff();
  const [reason, setReason] = useState("");
  const [suggest, setSuggest] = useState(NOBODY);
  const [touched, setTouched] = useState(false);

  const options = useMemo<SelectOption[]>(
    () => [
      { value: NOBODY, label: "Không gợi ý ai" },
      ...staff
        .filter((s) => s.id !== user.id)
        .map((s) => ({ value: s.id, label: s.name, hint: ROLE_LABEL[s.role] })),
    ],
    [staff, user.id],
  );
  const problem = touched ? declineError(reason) : "";

  function submit() {
    setTouched(true);
    if (declineError(reason)) return;
    onSubmit(reason.trim(), suggest === NOBODY ? null : suggest);
  }

  return (
    <Sheet
      title="Từ chối nhận cuộc trò chuyện"
      subtitle={patientName}
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Quay lại
          </SecondaryButton>
          <PrimaryButton onClick={submit} disabled={busy}>
            Gửi từ chối
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <Field
          label="Lý do"
          htmlFor="decline-reason"
          hint="Lý do giúp hệ thống chọn đúng người lần sau. Khách không thấy nội dung này."
        >
          <textarea
            id="decline-reason"
            className={cx(FIELD_BASE_CLASS, "min-h-24 w-full")}
            value={reason}
            maxLength={REASON_MAX}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => setTouched(true)}
            aria-invalid={problem !== ""}
            aria-describedby={problem ? "decline-reason-error" : undefined}
          />
          {problem && (
            <p id="decline-reason-error" role="alert" className="mt-1 text-label text-danger">
              {problem}
            </p>
          )}
        </Field>
        <Field
          label="Gợi ý đồng nghiệp nhận thay"
          htmlFor="decline-suggest"
          hint="Người được gợi ý sẽ được hỏi trước."
        >
          <SelectMenu
            id="decline-suggest"
            size="md"
            value={suggest}
            options={options}
            onChange={setSuggest}
            disabled={loading && staff.length === 0}
          />
        </Field>
        {staffError && (
          <Notice
            tone="warn"
            action={
              <button type="button" onClick={reload} className="min-h-9 px-2 text-small underline">
                Thử lại
              </button>
            }
          >
            Chưa đọc được danh sách đồng nghiệp. Bạn vẫn từ chối được mà không gợi ý ai.
          </Notice>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </div>
    </Sheet>
  );
}
