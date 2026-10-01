"use client";

// Create or edit a message template. A new or edited template is INACTIVE until a doctor approves it
// (`POST .../approve`); editing an approved one clears the approval, which the form says before saving.
import { useState, type FormEvent } from "react";

import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";

type Template = Schemas["MessageTemplateOut"];

const KEY_PATTERN = /^[a-z0-9][a-z0-9_.-]*$/;
const MAX_BODY = 2000;

export function TemplateSheet({
  template,
  onClose,
  onSaved,
}: {
  /** null = create a new template */
  template: Template | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [key, setKey] = useState(template?.template_key ?? "");
  const [title, setTitle] = useState(template?.title ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const [marketing, setMarketing] = useState(template?.marketing ?? false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const keyOk = template !== null || KEY_PATTERN.test(key);
  const wasApproved = template?.approved_at != null;
  const contentChanged =
    template !== null &&
    (title !== template.title || body !== template.body || marketing !== template.marketing);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!keyOk) {
      setError("Mã mẫu chỉ gồm chữ thường không dấu, số, gạch dưới, gạch ngang hoặc dấu chấm.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (template) {
        await unwrap(
          http.PATCH("/api/v1/admin/templates/{template_id}", {
            params: { path: { template_id: template.id } },
            body: { title: title.trim(), body: body.trim(), marketing, version: template.version },
          }),
        );
      } else {
        await unwrap(
          http.POST("/api/v1/admin/templates", {
            body: { template_key: key, title: title.trim(), body: body.trim(), marketing },
          }),
        );
      }
      toast.push("success", "Đã lưu mẫu. Mẫu cần bác sĩ duyệt trước khi dùng.");
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === "version_conflict"
          ? "Mẫu vừa được người khác sửa. Đóng form và mở lại."
          : errorMessage(err),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={template ? "Sửa mẫu tin nhắn" : "Soạn mẫu tin nhắn"}
      subtitle="Mẫu chỉ được dùng cho tin chủ động sau khi bác sĩ duyệt"
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton
            type="submit"
            form="template-form"
            disabled={busy || !title.trim() || !body.trim() || (!template && !key)}
          >
            {busy ? "Đang lưu..." : "Lưu mẫu"}
          </PrimaryButton>
        </>
      }
    >
      <form id="template-form" onSubmit={(e) => void submit(e)} className="space-y-4">
        {wasApproved && contentChanged && (
          <Notice tone="warn">
            Mẫu đã được bác sĩ duyệt. Sửa nội dung sẽ xóa chữ ký duyệt và tắt mẫu cho đến khi bác sĩ
            duyệt lại.
          </Notice>
        )}
        <Field
          label="Mã mẫu"
          htmlFor="tpl-key"
          hint={
            template
              ? "Mã không đổi được sau khi tạo."
              : "Ví dụ: nhac-tai-kham. Chữ thường, số, gạch ngang."
          }
        >
          <input
            id="tpl-key"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            disabled={template !== null}
            maxLength={64}
            className="gc-input w-full font-mono disabled:opacity-60"
          />
        </Field>
        <Field label="Tiêu đề" htmlFor="tpl-title">
          <input
            id="tpl-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            className="gc-input w-full"
          />
        </Field>
        <Field label="Nội dung" htmlFor="tpl-body" hint={`${body.length}/${MAX_BODY} ký tự`}>
          <textarea
            id="tpl-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={6}
            maxLength={MAX_BODY}
            className="gc-input w-full"
          />
        </Field>
        <label className="flex min-h-11 items-start gap-3 text-[13px]">
          <input
            type="checkbox"
            checked={marketing}
            onChange={(e) => setMarketing(e.target.checked)}
            className="mt-0.5 h-5 w-5 accent-brand-500"
          />
          <span>
            <span className="font-medium text-ink">Tin quảng bá</span>
            <span className="block text-ink-soft">
              Hệ thống chặn gửi cho khách đã từ chối tin quảng bá. Không dùng để chăm sóc an toàn
              sau điều trị.
            </span>
          </span>
        </label>
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}
