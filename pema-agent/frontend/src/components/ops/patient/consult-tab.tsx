"use client";

// Tư vấn tab: key points -> structured draft -> the clinician edits and approves it into Patient 360. Source of
// the behaviour: `consult`, `generate-note`, `approve-note` of prototype/shared/clinic.js. The draft is composed
// from a template by the BE (not by a model); nothing is part of the record until a clinician approves it.
import { useCallback, useState } from "react";

import { ClinicalNoteCard } from "@/components/ops/patient/clinical-note-card";
import { FormError, Muted, TEXTAREA_CLASS } from "@/components/ops/patient/shared";
import { ListSkeleton, Notice, PrimaryButton, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { Badge } from "@/ui/badge";
import { Card } from "@/ui/card";
import { Field } from "@/ui/field";
import { http, errorMessage, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/ops/format";
import { useLoad } from "@/lib/use-load";

export const POINTS_REQUIRED_MESSAGE = "Hãy nhập vài ý chính trước.";
export const DRAFT_EMPTY_MESSAGE = "Bản nháp không được để trống.";

export function ConsultTab({
  patientId,
  canWrite,
  onChanged,
}: {
  patientId: string;
  /** `session.write`: draft and approve. Without it the tab only lists the approved notes. */
  canWrite: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/consult-notes", {
          params: { path: { patient_id: patientId } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);
  const [points, setPoints] = useState("");
  const [edited, setEdited] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  const notes = data ?? [];
  const draft = notes.find((note) => note.status === "draft");
  const approved = notes.filter((note) => note.status === "approved");
  const draftText = draft === undefined ? "" : (edited[draft.id] ?? draft.body);

  async function createDraft() {
    if (points.trim() === "") {
      setProblem(POINTS_REQUIRED_MESSAGE);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/consult-notes", {
          params: { path: { patient_id: patientId } },
          body: { input_text: points.trim() },
        }),
      );
      setEdited({});
      setPoints("");
      toast.push("success", "Đã tạo bản nháp. Hãy kiểm tra trước khi duyệt.");
      reload();
    } catch (e) {
      setProblem(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (draft === undefined) return;
    if (draftText.trim() === "") {
      setProblem(DRAFT_EMPTY_MESSAGE);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/consult-notes/{note_id}/approve", {
          params: { path: { note_id: draft.id } },
          body: { version: draft.version, body: draftText.trim() },
        }),
      );
      setEdited({});
      toast.push("success", "Đã duyệt và nối vào Patient 360.");
      reload();
      onChanged();
    } catch (e) {
      setProblem(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (error !== "") return <RetryNotice message={error} onRetry={reload} />;
  if (loading && data === undefined) return <ListSkeleton rows={3} />;

  return (
    <div className="space-y-4">
      <ClinicalNoteCard patientId={patientId} canWrite={canWrite} onChanged={onChanged} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {canWrite && (
          <Card
            title="Tư vấn lâm sàng"
            subtitle="Bản ghi có người duyệt"
            aside={<Badge tone="brand">Đang soạn</Badge>}
          >
            <Notice tone="info">
              Bản nháp chỉ là gợi ý. Bác sĩ cần xem, sửa và xác nhận trước khi lưu vào hồ sơ.
            </Notice>
            <div className="mt-4">
              <Field label="Ghi chú ngắn: vài ý chính của buổi tư vấn">
                {(control) => (
                  <textarea
                    {...control}
                    value={points}
                    onChange={(e) => setPoints(e.target.value)}
                    placeholder="Ví dụ: Da ổn hơn, đỏ giảm sau 2 ngày..."
                    maxLength={2000}
                    className={TEXTAREA_CLASS}
                  />
                )}
              </Field>
            </div>
            <PrimaryButton disabled={busy} onClick={() => void createDraft()}>
              Tạo bản nháp ghi chú
            </PrimaryButton>
          </Card>
        )}

        <Card title="Bản nháp" subtitle="Được soạn từ các ý chính, chờ bác sĩ duyệt">
          {draft === undefined ? (
            <Muted>
              {canWrite
                ? "Chưa có bản nháp. Nhập vài ý chính bên cạnh để tạo bản nháp có cấu trúc."
                : "Chưa có bản nháp nào đang chờ duyệt."}
            </Muted>
          ) : (
            <div>
              <Field label="Chỉnh sửa bản nháp">
                {(control) => (
                  <textarea
                    {...control}
                    value={draftText}
                    readOnly={!canWrite}
                    onChange={(e) =>
                      setEdited((current) => ({ ...current, [draft.id]: e.target.value }))
                    }
                    maxLength={4000}
                    className={`${TEXTAREA_CLASS} min-h-44`}
                  />
                )}
              </Field>
              {canWrite && (
                <PrimaryButton disabled={busy} onClick={() => void approve()}>
                  ✓ Duyệt &amp; lưu vào Patient 360
                </PrimaryButton>
              )}
            </div>
          )}
          <FormError message={problem} />
        </Card>
      </div>

      <Card title="Ghi chú tư vấn đã duyệt" subtitle="Có người duyệt, nằm trong dòng thời gian">
        {approved.length === 0 && <Muted>Chưa có ghi chú tư vấn nào được duyệt.</Muted>}
        <ul className="space-y-3">
          {approved.map((note) => (
            <li key={note.id} className="rounded-control border border-line px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-x-2 text-label text-ink-soft">
                <span>{formatDateTime(note.approved_at)}</span>
                {note.approved_by_name !== null && note.approved_by_name !== undefined && (
                  <span>· {note.approved_by_name}</span>
                )}
              </div>
              <p className="mt-1 text-small break-words whitespace-pre-wrap text-ink">
                {note.body}
              </p>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
