"use client";

// "Nói với agent": a free-text instruction for the agent of this patient ("gọi khách bằng chị", "chỉ nhắn sau 18
// giờ"). The backend saves it as care memory with source `staff` after masking personal data; it is a preference
// for the agent, not a command that bypasses its limits (autonomy level, review, red flags still apply).
import { useId, useState } from "react";

import { Badge, SectionCard } from "@/components/admin/shared/ui-bits";
import { Field, Notice, PrimaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { errorMessage } from "@/lib/api/client";
import { careApi } from "@/lib/care/care-api";
import type { PatientCareTimeline } from "@/lib/care/care-types";
import { INSTRUCTION_MAX, instructionError } from "@/lib/care/forms";
import { MEMORY_SOURCE_LABEL } from "@/lib/care/labels";
import { formatDateTime } from "@/lib/ops/format";

export function TellAgentForm({
  patientId,
  timeline,
  onDone,
}: {
  patientId: string;
  timeline: PatientCareTimeline;
  onDone: () => void;
}) {
  const toast = useToast();
  const fieldId = useId();
  const [text, setText] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const problem = touched ? instructionError(text) : "";
  const told = timeline.memory.filter((m) => m.source === "staff");

  async function submit() {
    setTouched(true);
    if (instructionError(text)) return;
    setBusy(true);
    setError("");
    try {
      await careApi.tellAgent(patientId, text.trim());
      toast.push("success", "Agent đã ghi nhớ lời dặn.");
      setText("");
      setTouched(false);
      onDone();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <form
        className="gc-card space-y-4 p-4 sm:p-5"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field
          label="Lời dặn cho agent"
          htmlFor={fieldId}
          hint="Agent đọc lời dặn ở các lượt sau. Đây là thói quen hoặc ưu tiên của khách, không thay được mức tự chủ hay việc duyệt tin."
        >
          <textarea
            id={fieldId}
            className="gc-input min-h-28 w-full"
            value={text}
            maxLength={INSTRUCTION_MAX}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => setTouched(true)}
            aria-invalid={problem !== ""}
            aria-describedby={problem ? `${fieldId}-error` : undefined}
          />
          {problem && (
            <p id={`${fieldId}-error`} role="alert" className="mt-1 text-[12px] text-red-700">
              {problem}
            </p>
          )}
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
        <PrimaryButton type="submit" disabled={busy}>
          Lưu lời dặn
        </PrimaryButton>
      </form>

      <SectionCard title="Lời dặn đã lưu" subtitle="Của nhân viên cho agent của khách này">
        {told.length === 0 ? (
          <p className="text-[13px] text-ink-soft">Chưa có lời dặn nào.</p>
        ) : (
          <ul className="space-y-2">
            {told.map((fact) => (
              <li key={fact.id} className="flex flex-wrap items-start justify-between gap-2">
                <span className="min-w-0 flex-1 text-[14px] text-ink">{fact.fact}</span>
                <span className="flex items-center gap-2 text-[12px] text-ink-soft">
                  <Badge tone="gray" dot={false}>
                    {MEMORY_SOURCE_LABEL[fact.source]}
                  </Badge>
                  {formatDateTime(fact.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
