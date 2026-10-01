"use client";

// One review item: the AI draft with its sources, and the human decision (approve, edit then approve,
// reject, hand over to a doctor). Rules from AGENT.md and PLAN-AI01: an AI draft always shows where it
// came from, a person approves before anything reaches a patient, clinical items need a doctor, and the
// draft is never presented as a diagnosis. The BE enforces every one of them (`review_required`,
// `forbidden`); this component makes the right choice the easy one.
import Link from "next/link";
import { useCallback, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { Badge } from "@/components/admin/shared/ui-bits";
import {
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
  RiskBadge,
  SecondaryButton,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, newIdempotencyKey, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/ops/format";
import { REVIEW_KIND_LABEL, REVIEW_ORIGIN_LABEL, REVIEW_STATUS_LABEL } from "@/lib/ops/labels";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

const TEXT_KINDS: readonly Schemas["ReviewKind"][] = ["reply_draft", "followup_draft"];

const KIND_EXPLANATION: Partial<Record<Schemas["ReviewKind"], string>> = {
  triage_alert:
    "Tin của khách có dấu hiệu cần bác sĩ. Hệ thống đã dừng trả lời tự động và chưa gọi mô hình. Cần người liên hệ khách ngay.",
  media_flag:
    "Khách gửi ảnh hoặc tệp. Hệ thống không phân tích ảnh; mục này chuyển nhân viên xem ảnh trong ứng dụng Zalo và quyết định.",
  identity_check:
    "Tài khoản Zalo này chưa được gắn với hồ sơ bệnh nhân. Trợ lý AI chưa được nhắc tên, lịch hẹn hay thuốc cho đến khi nhân viên xác nhận.",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="mb-1.5 text-[11px] font-semibold tracking-wide text-ink-soft uppercase">
        {title}
      </h3>
      {children}
    </section>
  );
}

type Mode = "view" | "edit" | "reject" | "escalate";

export function ReviewDetail({
  itemId,
  patientName,
  onChanged,
}: {
  itemId: string;
  patientName: string;
  onChanged: () => void;
}) {
  const { can } = useSession();
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [mode, setMode] = useState<Mode>("view");
  const [editedText, setEditedText] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const [approveKey, setApproveKey] = useState(newIdempotencyKey);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/review-items/{item_id}", {
          params: { path: { item_id: itemId } },
          signal,
        }),
      ),
    [itemId],
  );
  const { data: item, error, loading, reload } = useLoad(load);

  const finish = useCallback(
    (message: string) => {
      toast.push("success", message);
      setMode("view");
      setNote("");
      setActionError("");
      setApproveKey(newIdempotencyKey());
      reload();
      onChanged();
    },
    [toast, reload, onChanged],
  );

  const run = useCallback(
    async (action: () => Promise<unknown>, done: string) => {
      setBusy(true);
      setActionError("");
      try {
        await action();
        finish(done);
      } catch (e) {
        const conflict = e instanceof ApiError && e.code === "version_conflict";
        setActionError(
          conflict ? "Mục này vừa được người khác xử lý. Đã tải lại." : errorMessage(e),
        );
        if (conflict) reload();
      } finally {
        setBusy(false);
      }
    },
    [finish, reload],
  );

  if (error && !item) return <RetryNotice message={error} onRetry={reload} />;
  if (!item) return loading ? <ListSkeleton rows={2} /> : null;

  const open = item.status === "pending" || item.status === "escalated";
  const hasText = TEXT_KINDS.includes(item.kind);
  const sources = item.sources ?? [];
  const redFlags = item.red_flags ?? [];
  const doctorBlocked = item.requires_doctor && !can("review.decide_clinical");
  const canDecide = can("review.decide") && open;
  const text = (mode === "edit" ? editedText : (item.draft_text ?? "")).trim();

  async function approve() {
    if (!item) return;
    const sendsToPatient = hasText;
    if (sendsToPatient) {
      const ok = await confirm({
        title: "Duyệt và gửi cho khách?",
        message: `Tin sau sẽ được gửi cho ${patientName}:\n\n${text}`,
        confirmLabel: "Duyệt và gửi",
        tone: "normal",
      });
      if (!ok) return;
    }
    await run(
      () =>
        unwrap(
          http.POST("/api/v1/review-items/{item_id}/approve", {
            params: { path: { item_id: item.id }, header: { "Idempotency-Key": approveKey } },
            body: {
              version: item.version,
              send: sendsToPatient,
              final_text: mode === "edit" ? editedText.trim() : undefined,
              note: note.trim() || undefined,
            },
          }),
        ),
      sendsToPatient ? "Đã duyệt và gửi cho khách." : "Đã đánh dấu đã xử lý.",
    );
  }

  async function reject() {
    if (!item) return;
    if (!note.trim()) {
      setActionError("Nhập lý do từ chối.");
      return;
    }
    await run(
      () =>
        unwrap(
          http.POST("/api/v1/review-items/{item_id}/reject", {
            params: { path: { item_id: item.id } },
            body: { version: item.version, reason: note.trim() },
          }),
        ),
      "Đã từ chối nháp.",
    );
  }

  async function escalate() {
    if (!item) return;
    await run(
      () =>
        unwrap(
          http.POST("/api/v1/review-items/{item_id}/escalate", {
            params: { path: { item_id: item.id } },
            body: { version: item.version, note: note.trim() || undefined },
          }),
        ),
      "Đã chuyển bác sĩ.",
    );
  }

  return (
    <article className="gc-card p-4 sm:p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[16px] font-semibold text-ink">{REVIEW_KIND_LABEL[item.kind]}</h2>
          <p className="mt-0.5 text-[13px] text-ink-soft">
            {item.patient_id ? (
              <Link href={`/patients/${item.patient_id}`} className="text-brand-500 underline">
                {patientName}
              </Link>
            ) : (
              patientName
            )}{" "}
            · {REVIEW_ORIGIN_LABEL[item.origin]} · {formatDateTime(item.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <RiskBadge risk={item.risk_level} />
          <Badge tone={item.status === "pending" ? "amber" : "gray"} dot={false}>
            {REVIEW_STATUS_LABEL[item.status]}
          </Badge>
          {item.requires_doctor && (
            <Badge tone="red" dot={false}>
              Cần bác sĩ
            </Badge>
          )}
        </div>
      </header>

      {redFlags.length > 0 && (
        <div className="mt-4">
          <Notice tone="error">
            Dấu hiệu cần bác sĩ:{" "}
            {redFlags.map((flag) => (
              <strong key={flag} className="mr-1.5">
                {flag}
              </strong>
            ))}
            . Không gửi lời khuyên tự động; cần người liên hệ khách.
          </Notice>
        </div>
      )}

      {KIND_EXPLANATION[item.kind] && (
        <div className="mt-4">
          <Notice tone="info">{KIND_EXPLANATION[item.kind]}</Notice>
        </div>
      )}

      {hasText && (
        <Section title="Nháp của trợ lý AI">
          {mode === "edit" ? (
            <>
              <label htmlFor="review-edit" className="sr-only">
                Sửa nội dung trước khi gửi
              </label>
              <textarea
                id="review-edit"
                value={editedText}
                onChange={(e) => setEditedText(e.target.value)}
                rows={6}
                maxLength={2000}
                className="gc-input w-full"
              />
              <p className="mt-1 text-[12px] text-ink-soft">
                Bản sửa được lưu cùng bản nháp gốc để đối chiếu.
              </p>
            </>
          ) : (
            <p className="rounded-lg bg-tile/60 px-3.5 py-3 text-[14px] leading-relaxed whitespace-pre-wrap text-ink">
              {item.final_text ?? item.draft_text}
            </p>
          )}
          <p className="mt-1.5 text-[12px] text-ink-soft">
            Nháp này không phải chẩn đoán hay chỉ định điều trị.
          </p>
        </Section>
      )}

      {hasText && (
        <Section title={`Nguồn trích dẫn (${sources.length})`}>
          {sources.length === 0 ? (
            <Notice tone="warn">
              Nháp không có nguồn trích dẫn. Kiểm tra kỹ nội dung, hoặc từ chối nếu không chắc.
            </Notice>
          ) : (
            <ul className="space-y-2">
              {sources.map((s) => (
                <li key={s.source_id} className="rounded-lg border border-line px-3 py-2.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[13px] font-semibold text-ink">{s.title}</span>
                    {typeof s.score === "number" && (
                      <span className="shrink-0 text-[11px] text-ink-soft">
                        độ khớp {Math.round(s.score * 100)}%
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-[13px] text-ink-soft">{s.snippet}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {item.model && (
        <p className="mt-3 text-[11px] text-ink-soft">
          Mô hình {item.model}
          {item.prompt_version ? ` · prompt ${item.prompt_version}` : ""}
        </p>
      )}

      {item.conversation_id && (
        <p className="mt-3 text-[13px]">
          <Link href={`/inbox?c=${item.conversation_id}`} className="text-brand-500 underline">
            Mở hội thoại với khách
          </Link>
        </p>
      )}

      {!open && (
        <Section title="Quyết định">
          <p className="text-[13px] text-ink">
            {REVIEW_STATUS_LABEL[item.status]} · {formatDateTime(item.decided_at)}
          </p>
          {item.decision_note && (
            <p className="mt-0.5 text-[13px] text-ink-soft">{item.decision_note}</p>
          )}
        </Section>
      )}

      {open && canDecide && (
        <div className="mt-5 border-t border-line pt-4">
          {doctorBlocked && (
            <div className="mb-3">
              <Notice tone="warn">
                Nội dung liên quan lâm sàng: chỉ bác sĩ được duyệt. Bạn có thể chuyển bác sĩ.
              </Notice>
            </div>
          )}

          {(mode === "reject" || mode === "escalate") && (
            <div className="mb-3">
              <label
                htmlFor="review-note"
                className="mb-1.5 block text-[13px] font-medium text-ink"
              >
                {mode === "reject" ? "Lý do từ chối (bắt buộc)" : "Ghi chú cho bác sĩ (nếu cần)"}
              </label>
              <textarea
                id="review-note"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                className="gc-input w-full"
              />
            </div>
          )}

          {actionError && (
            <div className="mb-3">
              <Notice tone="error">{actionError}</Notice>
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {mode === "view" && (
              <>
                <PrimaryButton
                  disabled={busy || doctorBlocked || (hasText && !text)}
                  onClick={() => void approve()}
                >
                  {hasText ? "Duyệt và gửi" : "Đánh dấu đã xử lý"}
                </PrimaryButton>
                {hasText && !doctorBlocked && (
                  <SecondaryButton
                    onClick={() => {
                      setEditedText(item.draft_text ?? "");
                      setMode("edit");
                    }}
                  >
                    Sửa rồi duyệt
                  </SecondaryButton>
                )}
                {hasText && !doctorBlocked && (
                  <SecondaryButton onClick={() => setMode("reject")}>Từ chối</SecondaryButton>
                )}
                {item.status === "pending" && !item.requires_doctor && (
                  <SecondaryButton onClick={() => setMode("escalate")}>
                    Chuyển bác sĩ
                  </SecondaryButton>
                )}
                {doctorBlocked && item.status === "pending" && (
                  <SecondaryButton onClick={() => setMode("escalate")}>
                    Chuyển bác sĩ
                  </SecondaryButton>
                )}
              </>
            )}
            {mode === "edit" && (
              <>
                <PrimaryButton disabled={busy || !editedText.trim()} onClick={() => void approve()}>
                  Duyệt bản đã sửa và gửi
                </PrimaryButton>
                <SecondaryButton onClick={() => setMode("view")}>Hủy sửa</SecondaryButton>
              </>
            )}
            {mode === "reject" && (
              <>
                <PrimaryButton disabled={busy} onClick={() => void reject()}>
                  Xác nhận từ chối
                </PrimaryButton>
                <SecondaryButton onClick={() => setMode("view")}>Quay lại</SecondaryButton>
              </>
            )}
            {mode === "escalate" && (
              <>
                <PrimaryButton disabled={busy} onClick={() => void escalate()}>
                  Chuyển bác sĩ
                </PrimaryButton>
                <SecondaryButton onClick={() => setMode("view")}>Quay lại</SecondaryButton>
              </>
            )}
          </div>
        </div>
      )}
      {confirmDialog}
    </article>
  );
}
