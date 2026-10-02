"use client";

// Return the conversation to the agent: a handover note and, optionally, a LOWER autonomy level for N days. The
// levels offered are the ones the backend lists (`release_levels`: a release never raises the level), the
// consequence under the form is the backend's own sentence (`POST .../release/preview`), and the backend refuses
// what it does not allow; this form holds no rule. Only the person who has the conversation can return it
// (`can_release`).
import { useEffect, useId, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { Field, Notice, PrimaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { errorMessage } from "@/lib/api/client";
import { careApi } from "@/lib/care/care-api";
import type { CareLevel, PatientCareTimeline, ReleasePreview } from "@/lib/care/care-types";
import { NOTE_MAX, releaseBody, releaseError, type ReleaseDraft } from "@/lib/care/forms";
import { CONTROL_LABEL, LEVEL_LABEL } from "@/lib/care/labels";

const PREVIEW_DELAY_MS = 300;
const KEEP = "" as const;

export function ReleaseForm({
  patientId,
  timeline,
  onDone,
}: {
  patientId: string;
  timeline: PatientCareTimeline;
  onDone: () => void;
}) {
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const noteId = useId();
  const daysId = useId();
  const [draft, setDraft] = useState<ReleaseDraft>({ note: "", level: KEEP, days: "7" });
  const [preview, setPreview] = useState<ReleasePreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const problem = releaseError(draft, timeline.max_override_days);
  const { level, days } = draft;

  useEffect(() => {
    if (!timeline.can_release || problem) {
      setPreview(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      careApi
        .previewRelease(patientId, releaseBody({ note: "", level, days }), controller.signal)
        .then((result) => {
          setPreview(result);
          setPreviewError("");
        })
        .catch((e: unknown) => {
          if (!controller.signal.aborted) setPreviewError(errorMessage(e));
        });
    }, PREVIEW_DELAY_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [patientId, timeline.can_release, problem, level, days]);

  if (!timeline.can_release) {
    return (
      <Notice tone="info">
        {timeline.control.state === "STAFF"
          ? "Chỉ người đang phụ trách cuộc trò chuyện mới trả lại cho agent được."
          : `Cuộc trò chuyện đang ở trạng thái "${CONTROL_LABEL[timeline.control.state]}", chưa có gì để trả lại.`}
      </Notice>
    );
  }

  async function submit() {
    if (problem || (preview && !preview.allowed)) return;
    const ok = await confirm({
      title: "Trả lại cho agent?",
      message: preview?.consequence ?? "Agent sẽ tiếp tục phụ trách cuộc trò chuyện này.",
      confirmLabel: "Trả lại",
      tone: "normal",
    });
    if (!ok) return;
    setBusy(true);
    setError("");
    try {
      await careApi.release(patientId, releaseBody(draft));
      toast.push("success", "Đã trả cuộc trò chuyện lại cho agent.");
      onDone();
    } catch (e) {
      setError(errorMessage(e));
      onDone();
    } finally {
      setBusy(false);
    }
  }

  const options: { value: CareLevel | ""; label: string }[] = [
    { value: KEEP, label: "Giữ mức hiện tại của agent" },
    ...timeline.release_levels.map((l) => ({
      value: l,
      label: `Hạ xuống ${LEVEL_LABEL[l]} trong một thời gian`,
    })),
  ];

  return (
    <form
      className="gc-card space-y-5 p-4 sm:p-5"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <Field
        label="Ghi chú bàn giao"
        htmlFor={noteId}
        hint="Agent đọc ghi chú này ở các lượt sau. Thông tin cá nhân được che trước khi lưu."
      >
        <textarea
          id={noteId}
          className="gc-input min-h-24 w-full"
          value={draft.note}
          maxLength={NOTE_MAX}
          onChange={(e) => setDraft({ ...draft, note: e.target.value })}
        />
      </Field>

      <fieldset>
        <legend className="mb-1.5 text-[13px] font-medium text-ink">
          Mức tự chủ sau khi trả lại
        </legend>
        <div className="space-y-1">
          {options.map((option) => (
            <label
              key={option.value || "keep"}
              className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-line px-3 py-2 has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50"
            >
              <input
                type="radio"
                name="release-level"
                checked={draft.level === option.value}
                onChange={() => setDraft({ ...draft, level: option.value })}
              />
              <span className="text-[14px] text-ink">{option.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {draft.level !== KEEP && (
        <Field
          label="Số ngày áp dụng"
          htmlFor={daysId}
          hint={`Sau thời hạn này agent tự về mức gốc. Tối đa ${timeline.max_override_days} ngày.`}
        >
          <input
            id={daysId}
            inputMode="numeric"
            className="gc-input w-28"
            value={draft.days}
            onChange={(e) => setDraft({ ...draft, days: e.target.value })}
            aria-invalid={problem !== ""}
          />
        </Field>
      )}

      {problem && <Notice tone="warn">{problem}</Notice>}
      {!problem && preview && (
        <Notice tone={preview.allowed ? "info" : "warn"}>
          <span className="font-medium">Hệ quả: </span>
          {preview.consequence}
        </Notice>
      )}
      {previewError && <Notice tone="error">{previewError}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}

      <PrimaryButton type="submit" disabled={busy || problem !== "" || preview?.allowed === false}>
        Trả lại cho agent
      </PrimaryButton>
      {confirmDialog}
    </form>
  );
}
