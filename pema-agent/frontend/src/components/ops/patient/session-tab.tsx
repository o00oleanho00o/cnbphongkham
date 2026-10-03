"use client";

// Buổi điều trị tab: the form of the old "Ghi buổi điều trị" (same fields as the `session-*` inputs of
// prototype/shared/clinic.js) and the list of recorded sessions. Saving completes the session on the BE: the plan
// counter, the arrived appointment, the recall date, and the milestones D+1/3/7 of the CRM all follow from it.
// A photo is uploaded after the session is saved, with the patient's consent (recorded here when the checkbox
// says the patient agreed and the BE has no consent yet).
import { useCallback, useMemo, useRef, useState, type FormEvent } from "react";

import { FormError, Muted, TEXTAREA_CLASS, TwoCol } from "@/components/ops/patient/shared";
import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { clinicDateKey, formatDate } from "@/lib/ops/format";
import {
  EXTRA_SESSION_TYPES,
  LASER_PROTOCOL_ID,
  PHOTO_REGIONS,
  PHOTO_VIEWS,
  PROTOCOL_OPTIONS,
} from "@/lib/ops/labels";
import { checkPhotoFile, uploadPhoto } from "@/lib/ops/media-upload";
import {
  defaultNextVisit,
  sessionCounterLabel,
  stageForNewPhoto,
  validateSessionForm,
  type SessionFormState,
} from "@/lib/ops/session-form";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Plan = Schemas["TreatmentPlanOut"];
type SessionDetail = Schemas["SessionDetailOut"];

const isLive = (plan: Plan): boolean => plan.status === "planned" || plan.status === "active";

function initialForm(plan: Plan | undefined, consentGranted: boolean): SessionFormState {
  return {
    planId: plan?.id ?? "",
    performedOn: clinicDateKey(),
    sessionType: plan?.title ?? "Buổi điều trị",
    protocolId: plan?.service_code === LASER_PROTOCOL_ID ? LASER_PROTOCOL_ID : "",
    nextVisitOn: defaultNextVisit(),
    note: "",
    aftercare: "",
    region: PHOTO_REGIONS[0],
    view: PHOTO_VIEWS[0],
    photoName: "",
    photoConsent: consentGranted,
  };
}

function SessionRow({ session }: { session: SessionDetail }) {
  return (
    <li className="rounded-control border border-line px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="min-w-0 text-small font-semibold break-words text-ink">
          {session.title}
        </span>
        <Badge tone={session.status === "completed" ? "success" : "neutral"} dot={false}>
          {session.status === "completed" ? "Đã hoàn tất" : "Chưa hoàn tất"}
        </Badge>
      </div>
      {session.note !== null && session.note !== undefined && (
        <p className="mt-1 line-clamp-3 text-small break-words text-ink-soft">{session.note}</p>
      )}
      <p className="mt-1 text-label text-ink-soft">
        {formatDate(session.performed_at)}
        {session.doctor_name ? ` · ${session.doctor_name}` : ""}
        {session.reviewed ? " · đã duyệt" : ""}
      </p>
    </li>
  );
}

export function SessionTab({
  patientId,
  plans,
  alerts,
  consentGranted,
  canWrite,
  canRecordConsent,
  canUpload,
  canReadMedia,
  onSaved,
}: {
  patientId: string;
  plans: Plan[];
  /** Sentence about the patient's risks to read before saving (allergy, reaction), if any. */
  alerts: string[];
  /** The patient's current media consent is a grant. */
  consentGranted: boolean;
  /** `session.write`: show the form. */
  canWrite: boolean;
  /** `consent.write`: the checkbox may record the consent. */
  canRecordConsent: boolean;
  /** `media.write`: a photo can be sent. */
  canUpload: boolean;
  /** `media.read`: the photos are counted to tell the first of an angle ("before") from the next ("after"). */
  canReadMedia: boolean;
  onSaved: () => void;
}) {
  const toast = useToast();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/sessions", {
          params: { path: { patient_id: patientId } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);
  const loadPhotos = useCallback(
    (signal: AbortSignal) =>
      canReadMedia
        ? unwrap(
            http.GET("/api/v1/patients/{patient_id}/media", {
              params: { path: { patient_id: patientId } },
              signal,
            }),
          )
        : Promise.resolve([]),
    [patientId, canReadMedia],
  );
  const { data: photos } = useLoad(loadPhotos);
  const photoCountForView = (view: string): number =>
    (photos ?? []).filter((m) => m.view === view).length;
  const livePlans = useMemo(() => plans.filter(isLive), [plans]);
  const [form, setForm] = useState<SessionFormState>(() =>
    initialForm(livePlans[0], consentGranted),
  );
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const sessions = data ?? [];
  const plan = plans.find((p) => p.id === form.planId);
  const progress =
    plan === undefined ? null : { completed: plan.completed_sessions, total: plan.total_sessions };
  const lastVisit =
    sessions
      .filter((s) => s.status === "completed")
      .map((s) => clinicDateKey(new Date(s.performed_at)))
      .toSorted()
      .at(-1) ?? null;
  const patch = (change: Partial<SessionFormState>) =>
    setForm((current) => ({ ...current, ...change }));

  function choosePlan(planId: string) {
    const chosen = plans.find((p) => p.id === planId);
    patch({
      planId,
      sessionType: chosen?.title ?? form.sessionType,
      protocolId: chosen?.service_code === LASER_PROTOCOL_ID ? LASER_PROTOCOL_ID : form.protocolId,
    });
  }

  function choosePhoto(chosen: File | null) {
    if (chosen === null) {
      setFile(null);
      patch({ photoName: "" });
      return;
    }
    const message = checkPhotoFile(chosen);
    if (message !== null) {
      setProblem(message);
      setFile(null);
      patch({ photoName: "" });
      if (fileInput.current !== null) fileInput.current.value = "";
      return;
    }
    setProblem("");
    setFile(chosen);
    // choosing a file un-ticks the consent unless the BE already holds it, like the old form
    patch({ photoName: chosen.name, photoConsent: consentGranted });
  }

  async function ensureConsent(): Promise<string | null> {
    if (consentGranted) return null;
    if (!canRecordConsent) {
      return "Người bệnh chưa có đồng ý hình ảnh. Nhờ lễ tân hoặc CSKH ghi nhận trước.";
    }
    try {
      await unwrap(
        http.POST("/api/v1/patients/{patient_id}/consents", {
          params: { path: { patient_id: patientId } },
          body: { kind: "media", granted: true, source: "Ghi nhận khi lưu buổi điều trị" },
        }),
      );
      return null;
    } catch (e) {
      return errorMessage(e);
    }
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const message = validateSessionForm(form, progress, lastVisit);
    if (message !== null) {
      setProblem(message);
      return;
    }
    setBusy(true);
    setProblem("");
    const consentProblem = file === null ? null : await ensureConsent();
    if (consentProblem !== null) {
      setProblem(consentProblem);
      setBusy(false);
      return;
    }
    try {
      const saved = await unwrap(
        http.POST("/api/v1/patients/{patient_id}/sessions", {
          params: { path: { patient_id: patientId } },
          body: {
            performed_on: form.performedOn,
            plan_id: form.planId === "" ? null : form.planId,
            session_type: form.sessionType,
            protocol_id: form.protocolId === "" ? null : form.protocolId,
            region: form.region,
            view: form.view,
            note: form.note.trim(),
            aftercare: form.aftercare.trim(),
            next_visit_on: form.nextVisitOn === "" ? null : form.nextVisitOn,
            complete: true,
            with_photo: file !== null,
          },
        }),
      );
      const uploadProblem = await sendPhoto(saved.id);
      toast.push("success", "Đã lưu buổi điều trị và cập nhật hành trình.");
      if (uploadProblem !== null) toast.push("error", uploadProblem);
      setForm(initialForm(livePlans[0], true));
      setFile(null);
      if (fileInput.current !== null) fileInput.current.value = "";
      reload();
      onSaved();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  /** The session is already saved when this runs, so a failure here is a sentence, not a failed save. */
  async function sendPhoto(sessionId: string): Promise<string | null> {
    if (file === null) return null;
    try {
      await uploadPhoto({
        patientId,
        file,
        stage: stageForNewPhoto(photoCountForView(form.view)),
        sessionId,
        region: form.region,
        view: form.view,
      });
      return null;
    } catch (e) {
      return `Buổi đã lưu nhưng chưa tải được ảnh: ${errorMessage(e)} Thêm ảnh ở tab Ảnh.`;
    }
  }

  const sessionTypes = [plan?.title ?? "Buổi điều trị", ...EXTRA_SESSION_TYPES];

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {canWrite && (
        <div className="min-w-0 lg:col-span-2">
          <Card
            title="Ghi buổi điều trị"
            subtitle="Tạo sự kiện mới trong hành trình của người bệnh"
            aside={
              <Badge tone="brand" dot={false}>
                {sessionCounterLabel(progress)}
              </Badge>
            }
          >
            <form onSubmit={(e) => void submit(e)} noValidate>
              <Field label="Kế hoạch">
                {(control) => (
                  <select
                    {...control}
                    value={form.planId}
                    onChange={(e) => choosePlan(e.target.value)}
                    className={FIELD_CONTROL_CLASS}
                  >
                    <option value="">Không gắn kế hoạch</option>
                    {plans.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title} ({p.completed_sessions}/{p.total_sessions})
                      </option>
                    ))}
                  </select>
                )}
              </Field>
              <TwoCol>
                <Field label="Ngày">
                  {(control) => (
                    <input
                      {...control}
                      type="date"
                      value={form.performedOn}
                      max={clinicDateKey()}
                      onChange={(e) => patch({ performedOn: e.target.value })}
                      className={FIELD_CONTROL_CLASS}
                    />
                  )}
                </Field>
                <Field label="Loại buổi">
                  {(control) => (
                    <select
                      {...control}
                      value={form.sessionType}
                      onChange={(e) => patch({ sessionType: e.target.value })}
                      className={FIELD_CONTROL_CLASS}
                    >
                      {sessionTypes.map((type) => (
                        <option key={type}>{type}</option>
                      ))}
                    </select>
                  )}
                </Field>
              </TwoCol>
              <TwoCol>
                <Field label="Protocol chăm sóc">
                  {(control) => (
                    <select
                      {...control}
                      value={form.protocolId}
                      onChange={(e) => patch({ protocolId: e.target.value })}
                      className={FIELD_CONTROL_CLASS}
                    >
                      {PROTOCOL_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Ngày dự kiến tái khám">
                  {(control) => (
                    <input
                      {...control}
                      type="date"
                      value={form.nextVisitOn}
                      min={clinicDateKey()}
                      onChange={(e) => patch({ nextVisitOn: e.target.value })}
                      className={FIELD_CONTROL_CLASS}
                    />
                  )}
                </Field>
              </TwoCol>
              <Field label="Đánh giá trước buổi">
                {(control) => (
                  <textarea
                    {...control}
                    value={form.note}
                    maxLength={2000}
                    placeholder="Tình trạng da, phản hồi, quyết định của bác sĩ..."
                    onChange={(e) => patch({ note: e.target.value })}
                    className={TEXTAREA_CLASS}
                  />
                )}
              </Field>
              <Field
                label="Hướng dẫn chăm sóc gửi sau buổi"
                hint="Lưu để nhân viên gửi theo mẫu đã duyệt; hệ thống không tự gửi."
              >
                {(control) => (
                  <textarea
                    {...control}
                    value={form.aftercare}
                    maxLength={2000}
                    onChange={(e) => patch({ aftercare: e.target.value })}
                    className={TEXTAREA_CLASS}
                  />
                )}
              </Field>
              <TwoCol>
                <Field label="Vùng chụp">
                  {(control) => (
                    <select
                      {...control}
                      value={form.region}
                      onChange={(e) => patch({ region: e.target.value })}
                      className={FIELD_CONTROL_CLASS}
                    >
                      {PHOTO_REGIONS.map((region) => (
                        <option key={region}>{region}</option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Góc chụp">
                  {(control) => (
                    <select
                      {...control}
                      value={form.view}
                      onChange={(e) => patch({ view: e.target.value })}
                      className={FIELD_CONTROL_CLASS}
                    >
                      {PHOTO_VIEWS.map((view) => (
                        <option key={view}>{view}</option>
                      ))}
                    </select>
                  )}
                </Field>
              </TwoCol>
              {canUpload && (
                <Field
                  label="Ảnh mốc"
                  hint="PNG, JPEG hoặc WebP, tối đa 8 MB. Hệ thống chỉ lưu ảnh, không phân tích ảnh."
                >
                  {(control) => (
                    <input
                      {...control}
                      ref={fileInput}
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(e) => choosePhoto(e.target.files?.[0] ?? null)}
                      className={`${FIELD_CONTROL_CLASS} file:mr-3 file:rounded-control file:border-0 file:bg-tile file:px-3 file:py-1.5`}
                    />
                  )}
                </Field>
              )}
              {canUpload && (
                <label className="mb-4 flex items-start gap-2.5 text-small text-ink-soft">
                  <input
                    type="checkbox"
                    checked={form.photoConsent}
                    onChange={(e) => patch({ photoConsent: e.target.checked })}
                    className="mt-0.5 h-4 w-4 shrink-0"
                  />
                  <span>Người bệnh đã có đồng ý phù hợp cho ảnh chăm sóc.</span>
                </label>
              )}
              <Button type="submit" disabled={busy}>
                ✓ Lưu buổi điều trị
              </Button>
              <FormError message={problem} />
            </form>
          </Card>
        </div>
      )}

      <div className={canWrite ? "min-w-0 space-y-4" : "min-w-0 space-y-4 lg:col-span-3"}>
        {canWrite && (
          <Notice tone={alerts.length > 0 ? "warn" : "info"}>
            {alerts.length > 0
              ? `Hồ sơ có cảnh báo: ${alerts.join(", ")}. Hãy xác nhận trước khi thực hiện.`
              : "Trước khi lưu: kiểm tra phản ứng sau buổi trước, ảnh mốc và hướng dẫn chăm sóc đã gửi."}
          </Notice>
        )}
        <Card title="Các buổi đã ghi">
          {error !== "" && <RetryNotice message={error} onRetry={reload} />}
          {loading && data === undefined && <ListSkeleton rows={2} />}
          {data !== undefined && sessions.length === 0 && <Muted>Chưa có buổi nào được ghi.</Muted>}
          <ul className="space-y-2">
            {sessions.map((session) => (
              <SessionRow key={session.id} session={session} />
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
