"use client";

// The dialogs of the Patient 360 header and cards (package U, step U9). Copy and fields are the ones of the old
// Clinic Web (`modalHtml` of prototype/shared/clinic.js, `crm-ui.js` "Ngày dự kiến quay lại"):
//   AI brief        "Brief trước buổi hẹn" (WC13, WC32)   a TEMPLATE over the records, no model; a doctor edits it
//   Nhắn tin        "Gửi cập nhật" (WC14)                 a note on the patient app timeline, no Zalo, no SMS
//   Chăm sóc tại nhà                    (WC16)            aftercare text on the patient app timeline
//   Thông tin cần nhớ                    (WC15)           one warning per line + the photo consent (U3 action)
//   Ngày dự kiến quay lại                (WC18, WC34)
// The BE decides every request and says the old sentence when it refuses; the forms check first so a mistake is
// told in place.
import { useCallback, useState, type FormEvent } from "react";

import { FormError, TEXTAREA_CLASS } from "@/components/ops/patient/shared";
import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { copyText } from "@/lib/ops/clipboard";
import {
  AFTERCARE_BLANK,
  BRIEF_BLANK,
  EXPECTED_RETURN_INVALID,
  EXPECTED_SOURCE_OPTIONS,
  MAX_ALERTS,
  MESSAGE_BLANK,
  NO_CLIPBOARD,
  alertsProblem,
  expectedReturnProblem,
  splitAlerts,
} from "@/lib/ops/patient-profile";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { Sheet } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type P360 = Schemas["Patient360"];

const SOURCE_LINE = "Nguồn: Patient 360, events đã ghi nhận, follow-up đang mở.";

function lastWord(name: string): string {
  return name.trim().split(/\s+/).at(-1) ?? name;
}

// ----------------------------------------------------------------------------------------------- brief
export function BriefDialog({ data, onClose }: { data: P360; onClose: () => void }) {
  const toast = useToast();
  const patientId = data.patient.id;
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/brief", {
          params: { path: { patient_id: patientId } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data: draft, error, loading, reload } = useLoad(load);
  const [edited, setEdited] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const text = edited ?? draft?.text ?? "";
  const plan = (data.plans ?? []).at(0);

  async function copy() {
    const ok = await copyText(text);
    if (ok) toast.push("success", "Đã sao chép brief");
    else toast.push("error", NO_CLIPBOARD);
  }

  async function approve() {
    if (text.trim() === "") {
      setProblem(BRIEF_BLANK);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/brief/approve", {
          params: { path: { patient_id: patientId } },
          body: { text: text.trim() },
        }),
      );
      toast.push("success", "Đã lưu brief có bác sĩ duyệt và nguồn sự kiện");
      onClose();
    } catch (e) {
      setProblem(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Brief trước buổi hẹn"
      subtitle="Bản nháp ghép từ hồ sơ, không do mô hình viết"
      wide
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={() => void copy()} disabled={draft === undefined}>
            Sao chép
          </Button>
          <Button onClick={() => void approve()} disabled={busy || draft === undefined}>
            Duyệt &amp; lưu brief
          </Button>
        </>
      }
    >
      <h3 className="mb-2 text-body font-semibold text-heading">
        {data.patient.full_name}
        {plan ? ` · ${plan.title}` : ""}
      </h3>
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && draft === undefined && <ListSkeleton rows={2} />}
      {draft !== undefined && (
        <>
          <Field label="Brief mô phỏng · sửa trước khi duyệt">
            {(control) => (
              <textarea
                {...control}
                value={text}
                onChange={(e) => setEdited(e.target.value)}
                maxLength={4000}
                className={`${TEXTAREA_CLASS} min-h-44`}
              />
            )}
          </Field>
          {draft.approved && (
            <p className="mb-2 text-label text-ink-soft">
              Bản đã duyệt gần nhất
              {draft.approved.approved_by_name
                ? ` bởi ${draft.approved.approved_by_name}`
                : ""}: {draft.approved.source_ids.length} nguồn ghi nhận.
            </p>
          )}
          <Notice>{SOURCE_LINE} Bác sĩ cần xác nhận trước khi dùng trong chăm sóc.</Notice>
        </>
      )}
      <FormError message={problem} />
    </Sheet>
  );
}

// ---------------------------------------------------------------------------- Nhắn tin / Chăm sóc tại nhà
export function MessageDialog({
  data,
  onClose,
  onSent,
}: {
  data: P360;
  onClose: () => void;
  onSent: () => void;
}) {
  const toast = useToast();
  const [body, setBody] = useState(
    `Chào bạn ${lastWord(data.patient.full_name)}, Pema đã xem cập nhật của bạn. Da đang được theo dõi theo kế hoạch.`,
  );
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (body.trim() === "") {
      setProblem(MESSAGE_BLANK);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/app-updates", {
          params: { path: { patient_id: data.patient.id } },
          body: { kind: "message", body: body.trim() },
        }),
      );
      toast.push("success", "Đã gửi tin nhắn");
      onSent();
      onClose();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Gửi cập nhật"
      subtitle={`Tin nhắn · ${data.patient.full_name}`}
      onClose={onClose}
      footer={
        <Button type="submit" form="message-form" disabled={busy}>
          Gửi tin nhắn
        </Button>
      }
    >
      <form id="message-form" onSubmit={(e) => void submit(e)} noValidate>
        <Field label="Nội dung">
          {(control) => (
            <textarea
              {...control}
              value={body}
              maxLength={2000}
              onChange={(e) => setBody(e.target.value)}
              className={TEXTAREA_CLASS}
            />
          )}
        </Field>
        <p className="text-label text-ink-soft">
          Tin hiện trên dòng thời gian của app người bệnh. Không gửi qua Zalo hoặc SMS.
        </p>
        <FormError message={problem} />
      </form>
    </Sheet>
  );
}

export function AftercareDialog({
  patientId,
  onClose,
  onSent,
}: {
  patientId: string;
  onClose: () => void;
  onSent: () => void;
}) {
  const toast = useToast();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/app-updates", {
          params: { path: { patient_id: patientId }, query: { kind: "aftercare" } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);
  const [edited, setEdited] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const body = edited ?? data?.at(0)?.body ?? "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (body.trim() === "") {
      setProblem(AFTERCARE_BLANK);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/app-updates", {
          params: { path: { patient_id: patientId } },
          body: { kind: "aftercare", body: body.trim() },
        }),
      );
      toast.push("success", "Đã gửi hướng dẫn vào patient app");
      onSent();
      onClose();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Chăm sóc tại nhà"
      onClose={onClose}
      footer={
        <Button type="submit" form="aftercare-form" disabled={busy || data === undefined}>
          Duyệt &amp; gửi patient app
        </Button>
      }
    >
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && data === undefined && <ListSkeleton rows={2} />}
      {data !== undefined && (
        <form id="aftercare-form" onSubmit={(e) => void submit(e)} noValidate>
          <Field label="Hướng dẫn đã duyệt cho người bệnh">
            {(control) => (
              <textarea
                {...control}
                value={body}
                maxLength={2000}
                onChange={(e) => setEdited(e.target.value)}
                className={TEXTAREA_CLASS}
              />
            )}
          </Field>
          <FormError message={problem} />
        </form>
      )}
    </Sheet>
  );
}

// -------------------------------------------------------------------------------------- Thông tin cần nhớ
export function FactsDialog({
  data,
  canRecordConsent,
  onClose,
  onSaved,
}: {
  data: P360;
  /** `consent.write`: the checkbox is read only without it. */
  canRecordConsent: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const consent = (data.consents ?? []).find((c) => c.kind === "media");
  const granted = consent?.granted === true;
  const [alerts, setAlerts] = useState((data.alerts ?? []).join("\n"));
  const [photoConsent, setPhotoConsent] = useState(granted);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const lines = splitAlerts(alerts);
    const message = alertsProblem(lines);
    if (message !== null) {
      setProblem(message);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.PUT("/api/v1/patients/{patient_id}/alerts", {
          params: { path: { patient_id: data.patient.id } },
          body: { alerts: lines },
        }),
      );
      if (canRecordConsent && photoConsent !== granted) {
        await unwrap(
          http.POST("/api/v1/patients/{patient_id}/consents", {
            params: { path: { patient_id: data.patient.id } },
            body: { kind: "media", granted: photoConsent, source: "Patient 360" },
          }),
        );
      }
      toast.push("success", "Đã lưu thông tin");
      onSaved();
      onClose();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Thông tin cần nhớ"
      onClose={onClose}
      footer={
        <Button type="submit" form="facts-form" disabled={busy}>
          Lưu thông tin
        </Button>
      }
    >
      <form id="facts-form" onSubmit={(e) => void submit(e)} noValidate>
        <Field label="Cảnh báo · mỗi dòng một mục" hint={`Tối đa ${MAX_ALERTS} dòng.`}>
          {(control) => (
            <textarea
              {...control}
              value={alerts}
              onChange={(e) => setAlerts(e.target.value)}
              className={TEXTAREA_CLASS}
            />
          )}
        </Field>
        <label className="flex min-h-11 items-center gap-2 text-body text-ink">
          <input
            type="checkbox"
            checked={photoConsent}
            disabled={!canRecordConsent}
            onChange={(e) => setPhotoConsent(e.target.checked)}
            className="size-4 accent-brand-500"
          />
          Có đồng ý sử dụng ảnh chăm sóc
        </label>
        <FormError message={problem} />
      </form>
    </Sheet>
  );
}

// ------------------------------------------------------------------------------ Ngày dự kiến quay lại
export function ExpectedReturnDialog({
  data,
  onClose,
  onSaved,
}: {
  data: P360;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const { profile } = data;
  const known = EXPECTED_SOURCE_OPTIONS.some((o) => o.value === profile.expected_visit_source);
  const [form, setForm] = useState({
    date: profile.expected_next_visit_at ?? "",
    reason: "",
    source: known ? (profile.expected_visit_source ?? "") : "doctor_recommendation",
  });
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const patch = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (expectedReturnProblem(form) !== null) {
      setProblem(EXPECTED_RETURN_INVALID);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.PUT("/api/v1/patients/{patient_id}/expected-return", {
          params: { path: { patient_id: data.patient.id } },
          body: { date: form.date, reason: form.reason.trim(), source: form.source },
        }),
      );
      toast.push("success", "Đã cập nhật ngày dự kiến");
      onSaved();
      onClose();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Ngày dự kiến quay lại"
      onClose={onClose}
      footer={
        <Button type="submit" form="expected-form" disabled={busy}>
          Lưu ngày dự kiến
        </Button>
      }
    >
      <form id="expected-form" onSubmit={(e) => void submit(e)} noValidate>
        <Field label="Ngày bác sĩ/CSKH khuyến nghị" required>
          {(control) => (
            <input
              {...control}
              type="date"
              value={form.date}
              onChange={(e) => patch({ date: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Lý do" required>
          {(control) => (
            <input
              {...control}
              value={form.reason}
              maxLength={200}
              onChange={(e) => patch({ reason: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Nguồn">
          {(control) => (
            <select
              {...control}
              value={form.source}
              onChange={(e) => patch({ source: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            >
              {EXPECTED_SOURCE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Notice>
          Nếu đã có lịch thực tế, Patient 360 ưu tiên ngày lịch đó. Khuyến nghị vẫn được giữ khi hủy
          lịch.
        </Notice>
        <FormError message={problem} />
      </form>
    </Sheet>
  );
}
