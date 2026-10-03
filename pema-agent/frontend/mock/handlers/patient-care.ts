// Mock of the Patient 360 tab API: plans, sessions, consult notes, photos (package U, step U3). It repeats the
// BE rules the screens depend on (plan full, assessment and aftercare required, date window, consent before an
// upload, size and type, one open draft) so the forms can be exercised; the authority is the BE.
import { consents, patientById } from "../data/clinic";
import {
  media,
  notes,
  plans,
  publicMedia,
  sessions,
  sessionsOf,
  type StoredMedia,
} from "../data/patient-care";
import {
  fail,
  isoFromNow,
  uid,
  bodyOf,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
  type Session,
} from "../core";
import { USERS } from "../auth";

type S = Schemas;

const PHOTO_MAX_BYTES = 8 * 1024 * 1024;
const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
const VERSION_CONFLICT = "Bản ghi vừa được người khác cập nhật. Tải lại rồi thử lại.";

function session(ctx: Ctx): Session {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

const nameOf = (userId: string): string | null =>
  USERS.find((u) => u.id === userId)?.display_name ?? null;

function patientOr404(id: string): S["PatientOut"] {
  const found = patientById(id);
  if (!found) fail(404, "not_found", "Không tìm thấy bệnh nhân.");
  return found;
}

function checkVersion(current: number | undefined, sent: number): void {
  if ((current ?? 1) !== sent) fail(409, "version_conflict", VERSION_CONFLICT);
}

const today = (): string => isoFromNow(0).slice(0, 10);

function mediaConsentGranted(patientId: string): boolean {
  return (consents[patientId] ?? []).some((c) => c.kind === "media" && c.granted);
}

/** `care staff only for the patients they look after`: the mock patients all belong to Mai Anh. */
function assertScope(ctx: Ctx, patient: S["PatientOut"]): void {
  const s = session(ctx);
  if (s.role === "cs_staff" && patient.cs_owner_id !== s.userId) {
    fail(403, "forbidden", "Hồ sơ này không thuộc người bệnh bạn phụ trách.");
  }
}

// ------------------------------------------------------------------------------------------- sessions

function finishSession(row: S["SessionDetailOut"], userId: string, withPhoto: boolean): void {
  void withPhoto;
  const plan = plans.find((p) => p.id === row.plan_id);
  if (plan) {
    if (plan.completed_sessions >= plan.total_sessions) {
      fail(
        409,
        "invalid_state",
        "Kế hoạch đã đủ buổi. Hãy điều chỉnh kế hoạch trước khi thêm buổi mới.",
      );
    }
    plan.completed_sessions += 1;
    plan.version = (plan.version ?? 1) + 1;
    plan.status = plan.completed_sessions >= plan.total_sessions ? "completed" : "active";
  }
  row.title = plan
    ? `Buổi ${plan.completed_sessions}/${plan.total_sessions} · ${row.session_type ?? "Buổi điều trị"}`
    : (row.session_type ?? "Buổi điều trị");
  row.status = "completed";
  row.reviewed = true;
  row.reviewed_by = userId;
  row.reviewed_at = isoFromNow(0);
  row.version = (row.version ?? 1) + 1;
}

function assertCompletable(
  input: { note: string; aftercare: string; day: string },
  patientId: string,
  exclude?: string,
): void {
  if (input.note.trim() === "") fail(422, "validation_failed", "Hãy ghi đánh giá trước buổi.");
  if (input.aftercare.trim() === "")
    fail(422, "validation_failed", "Hãy nhập hướng dẫn chăm sóc sau buổi.");
  if (input.day > today()) fail(422, "validation_failed", "Ngày buổi không được ở tương lai.");
  const last = sessionsOf(patientId)
    .filter((s) => s.status === "completed" && s.id !== exclude)
    .map((s) => s.performed_at.slice(0, 10))
    .toSorted()
    .at(-1);
  if (last && input.day < last) {
    fail(422, "validation_failed", "Ngày buổi không được trước buổi điều trị gần nhất.");
  }
}

function createSession(ctx: Ctx): Reply {
  const user = session(ctx);
  const patient = patientOr404(ctx.params.patient_id ?? "");
  const input = bodyOf<S["SessionCreate"]>(ctx);
  const plan = input.plan_id
    ? plans.find((p) => p.id === input.plan_id && p.patient_id === patient.id)
    : undefined;
  if (input.plan_id && !plan)
    fail(422, "validation_failed", "Kế hoạch không thuộc người bệnh này.");
  const complete = input.complete ?? true;
  if (complete) {
    assertCompletable(
      { note: input.note ?? "", aftercare: input.aftercare ?? "", day: input.performed_on },
      patient.id,
    );
  }
  const row: S["SessionDetailOut"] = {
    id: uid("session"),
    patient_id: patient.id,
    plan_id: plan?.id ?? null,
    performed_at: `${input.performed_on}T12:00:00+07:00`,
    doctor_id: user.userId,
    doctor_name: nameOf(user.userId),
    protocol_id: input.protocol_id ?? null,
    title: input.session_type,
    status: "scheduled",
    session_type: input.session_type,
    region: input.region ?? null,
    view: input.view ?? null,
    next_visit_on: input.next_visit_on ?? null,
    note: (input.note ?? "").trim() || null,
    aftercare: (input.aftercare ?? "").trim() || null,
    reviewed: false,
    reviewed_by: null,
    reviewed_at: null,
    consent_id: null,
    version: 1,
  };
  if (complete) finishSession(row, user.userId, input.with_photo ?? false);
  sessions.unshift(row);
  return { status: 201, body: row };
}

function completeSession(ctx: Ctx): Reply {
  const user = session(ctx);
  const row = sessions.find((s) => s.id === ctx.params.session_id);
  if (!row) fail(404, "not_found", "Không tìm thấy buổi điều trị.");
  const input = bodyOf<S["SessionComplete"]>(ctx);
  checkVersion(row.version, input.version);
  if (row.status !== "scheduled")
    fail(409, "invalid_state", "Buổi điều trị này đã được hoàn tất hoặc đã hủy.");
  row.note = input.note ?? row.note ?? null;
  row.aftercare = input.aftercare ?? row.aftercare ?? null;
  assertCompletable(
    {
      note: row.note ?? "",
      aftercare: row.aftercare ?? "",
      day: input.performed_on ?? row.performed_at.slice(0, 10),
    },
    row.patient_id,
    row.id,
  );
  finishSession(row, user.userId, input.with_photo ?? false);
  return { body: row };
}

function reviewSession(ctx: Ctx): Reply {
  const user = session(ctx);
  const row = sessions.find((s) => s.id === ctx.params.session_id);
  if (!row) fail(404, "not_found", "Không tìm thấy buổi điều trị.");
  const input = bodyOf<S["SessionReview"]>(ctx);
  if (row.status !== "completed") fail(409, "invalid_state", "Chỉ buổi đã hoàn tất mới cần duyệt.");
  if (!row.reviewed) {
    checkVersion(row.version, input.version);
    row.reviewed = true;
    row.reviewed_by = user.userId;
    row.reviewed_at = isoFromNow(0);
    row.version = (row.version ?? 1) + 1;
  }
  return { body: row };
}

// -------------------------------------------------------------------------------------------- photos

function intent(ctx: Ctx): Reply {
  const user = session(ctx);
  const patient = patientOr404(ctx.params.patient_id ?? "");
  assertScope(ctx, patient);
  const input = bodyOf<S["MediaUploadIntent"]>(ctx);
  if (!PHOTO_TYPES.includes(input.mime))
    fail(422, "validation_failed", "Chỉ nhận ảnh PNG, JPEG hoặc WebP.");
  if (input.size_bytes > PHOTO_MAX_BYTES) fail(413, "payload_too_large", "Ảnh vượt quá 8 MB.");
  if (!mediaConsentGranted(patient.id)) {
    fail(
      422,
      "consent_required",
      "Cần ghi nhận đồng ý hình ảnh của người bệnh trước khi tải ảnh lên.",
    );
  }
  const id = uid("media");
  const row: StoredMedia = {
    id,
    patient_id: patient.id,
    session_id: input.session_id ?? null,
    stage: input.stage,
    region: input.region ?? null,
    view: input.view ?? null,
    mime: input.mime,
    size_bytes: input.size_bytes,
    status: "pending",
    consent_id: uid("consent"),
    consent_active: true,
    uploaded_by: user.userId,
    uploaded_by_name: nameOf(user.userId),
    created_at: isoFromNow(0),
    confirmed_at: null,
    content_path: `/api/v1/media/${id}/content`,
    version: 1,
    bytes: null,
    declaredSize: input.size_bytes,
  };
  media.push(row);
  const body: S["MediaUploadTarget"] = {
    media_id: id,
    upload_path: `/api/v1/media/${id}/content?exp=${Math.floor(Date.now() / 1000) + 600}&sig=mock`,
    method: "PUT",
    mime: input.mime,
    max_bytes: PHOTO_MAX_BYTES,
    expires_at: isoFromNow(10 * 60_000),
  };
  return { status: 201, body };
}

function putContent(ctx: Ctx): Reply {
  const row = media.find((m) => m.id === ctx.params.media_id);
  if (!row) fail(404, "not_found", "Không tìm thấy ảnh.");
  if (row.status !== "pending") fail(409, "invalid_state", "Ảnh này đã được tải lên.");
  if (!mediaConsentGranted(row.patient_id)) {
    fail(
      422,
      "consent_required",
      "Cần ghi nhận đồng ý hình ảnh của người bệnh trước khi tải ảnh lên.",
    );
  }
  if (ctx.raw.length !== row.declaredSize)
    fail(422, "validation_failed", "Dung lượng ảnh không khớp với khai báo.");
  row.bytes = ctx.raw;
  row.status = "uploaded";
  return { body: publicMedia(row) };
}

function confirm(ctx: Ctx): Reply {
  const row = media.find((m) => m.id === ctx.params.media_id);
  if (!row) fail(404, "not_found", "Không tìm thấy ảnh.");
  if (row.status === "confirmed") return { body: publicMedia(row) };
  if (row.status !== "uploaded") fail(409, "invalid_state", "Ảnh chưa được tải lên xong.");
  row.status = "confirmed";
  row.confirmed_at = isoFromNow(0);
  row.version = (row.version ?? 1) + 1;
  return { body: publicMedia(row) };
}

function content(ctx: Ctx): Reply {
  const row = media.find((m) => m.id === ctx.params.media_id);
  if (!row || row.bytes === null || row.status === "pending")
    fail(404, "not_found", "Không tìm thấy ảnh.");
  const patient = patientOr404(row.patient_id);
  assertScope(ctx, patient);
  const role = session(ctx).role;
  if (role !== "owner" && role !== "doctor" && !mediaConsentGranted(row.patient_id)) {
    fail(422, "consent_required", "Người bệnh chưa đồng ý hoặc đã rút đồng ý hình ảnh.");
  }
  return {
    raw: row.bytes,
    headers: { "content-type": row.mime, "cache-control": "private, no-store" },
  };
}

// ----------------------------------------------------------------------------------------------- notes

function composeDraft(points: string): string {
  const d = new Date(Date.now() + 7 * 3_600_000);
  const label = `${String(d.getUTCDate()).padStart(2, "0")}/${String(d.getUTCMonth() + 1).padStart(2, "0")}/${d.getUTCFullYear()}`;
  return `Bản nháp ghi chú · ${label}: ${points.trim()} Đáp ứng cần được đối chiếu với ảnh mốc và phản hồi của người bệnh. Kế hoạch tiếp theo cần bác sĩ xác nhận.`;
}

export function register(r: Router): void {
  // plans
  r.get("/api/v1/patients/{patient_id}/plans", "patient.read_360", (ctx): Reply => ({
    body: plans
      .filter((p) => p.patient_id === patientOr404(ctx.params.patient_id ?? "").id)
      .map(({ patient_id: _patient, ...plan }) => plan),
  }));
  r.post("/api/v1/patients/{patient_id}/plans", "session.write", (ctx): Reply => {
    const patient = patientOr404(ctx.params.patient_id ?? "");
    const input = bodyOf<S["PlanCreate"]>(ctx);
    const created = {
      id: uid("plan"),
      patient_id: patient.id,
      episode_id: input.episode_id ?? null,
      service_code: input.service_code,
      title: input.title,
      goal: input.goal ?? null,
      total_sessions: input.total_sessions,
      completed_sessions: 0,
      status: "active",
      doctor_id: session(ctx).userId,
      version: 1,
    };
    plans.push(created);
    const { patient_id: _patient, ...plan } = created;
    return { status: 201, body: plan };
  });
  r.patch("/api/v1/plans/{plan_id}", "session.write", (ctx): Reply => {
    const plan = plans.find((p) => p.id === ctx.params.plan_id);
    if (!plan) fail(404, "not_found", "Không tìm thấy kế hoạch.");
    const input = bodyOf<S["PlanUpdate"]>(ctx);
    checkVersion(plan.version, input.version);
    if (input.total_sessions !== undefined && input.total_sessions !== null) {
      if (input.total_sessions < plan.completed_sessions) {
        fail(422, "validation_failed", "Tổng số buổi không được thấp hơn số buổi đã hoàn tất.");
      }
      plan.total_sessions = input.total_sessions;
      plan.status = plan.completed_sessions >= plan.total_sessions ? "completed" : "active";
    }
    if (input.title) plan.title = input.title;
    if (input.goal !== undefined) plan.goal = input.goal;
    plan.version = (plan.version ?? 1) + 1;
    const { patient_id: _patient, ...out } = plan;
    return { body: out };
  });

  // sessions
  r.get("/api/v1/patients/{patient_id}/sessions", "session.read", (ctx): Reply => {
    const patient = patientOr404(ctx.params.patient_id ?? "");
    assertScope(ctx, patient);
    return { body: sessionsOf(patient.id) };
  });
  r.post("/api/v1/patients/{patient_id}/sessions", "session.write", createSession);
  r.post("/api/v1/sessions/{session_id}/complete", "session.write", completeSession);
  r.post("/api/v1/sessions/{session_id}/review", "session.write", reviewSession);

  // consult notes
  r.get("/api/v1/patients/{patient_id}/consult-notes", "session.read", (ctx): Reply => {
    const patient = patientOr404(ctx.params.patient_id ?? "");
    assertScope(ctx, patient);
    return {
      body: notes
        .filter((n) => n.patient_id === patient.id)
        .toSorted((a, b) => b.created_at.localeCompare(a.created_at)),
    };
  });
  r.post("/api/v1/patients/{patient_id}/consult-notes", "session.write", (ctx): Reply => {
    const user = session(ctx);
    const patient = patientOr404(ctx.params.patient_id ?? "");
    const input = bodyOf<S["ConsultNoteDraftCreate"]>(ctx);
    if (input.input_text.trim() === "")
      fail(422, "validation_failed", "Hãy nhập vài ý chính trước.");
    const open = notes.find((n) => n.patient_id === patient.id && n.status === "draft");
    if (open) {
      open.source_text = input.input_text.trim();
      open.body = composeDraft(input.input_text);
      open.version += 1;
      return { status: 201, body: open };
    }
    const created: S["ConsultNoteOut"] = {
      id: uid("note"),
      patient_id: patient.id,
      status: "draft",
      source_text: input.input_text.trim(),
      body: composeDraft(input.input_text),
      created_by: user.userId,
      created_by_name: nameOf(user.userId),
      approved_by: null,
      approved_by_name: null,
      approved_at: null,
      created_at: isoFromNow(0),
      version: 1,
    };
    notes.unshift(created);
    return { status: 201, body: created };
  });
  r.post("/api/v1/consult-notes/{note_id}/approve", "session.write", (ctx): Reply => {
    const user = session(ctx);
    const note = notes.find((n) => n.id === ctx.params.note_id);
    if (!note) fail(404, "not_found", "Không tìm thấy ghi chú tư vấn.");
    const input = bodyOf<S["ConsultNoteApprove"]>(ctx);
    checkVersion(note.version, input.version);
    if (note.status !== "draft") fail(409, "invalid_state", "Ghi chú này đã được duyệt.");
    const body = (input.body ?? note.body).trim();
    if (body === "") fail(422, "validation_failed", "Bản nháp không được để trống.");
    note.body = body;
    note.status = "approved";
    note.approved_by = user.userId;
    note.approved_by_name = nameOf(user.userId);
    note.approved_at = isoFromNow(0);
    note.version += 1;
    return { body: note };
  });

  // photos
  r.post("/api/v1/patients/{patient_id}/media/upload-intent", "media.write", intent);
  r.put("/api/v1/media/{media_id}/content", "media.write", putContent);
  r.post("/api/v1/media/{media_id}/confirm", "media.write", confirm);
  r.get("/api/v1/patients/{patient_id}/media", "media.read", (ctx): Reply => {
    const patient = patientOr404(ctx.params.patient_id ?? "");
    assertScope(ctx, patient);
    const sessionId = ctx.query.get("session_id");
    const active = mediaConsentGranted(patient.id);
    return {
      body: media
        .filter((m) => m.patient_id === patient.id && m.status !== "pending")
        .filter((m) => !sessionId || m.session_id === sessionId)
        .map((m) => ({ ...publicMedia(m), consent_active: active })),
    };
  });
  r.get("/api/v1/media/{media_id}/content", "media.read", content);
}
