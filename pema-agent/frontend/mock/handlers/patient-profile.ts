// Mock of the Patient 360 dialogs and cards of package U, step U9. It repeats the rules the screens depend on (the
// old sentences, the permission of each action, a price fixed on a course and shown only with a finance
// permission, a templated brief) so the dialogs can be exercised; the authority is the BE.
import { appointments, patientById, tasks } from "../data/clinic";
import { services } from "../data/catalog";
import { plans, sessionsOf } from "../data/patient-care";
import {
  alertsByPatient,
  appUpdates,
  briefs,
  clinicalNotes,
  type StoredAppUpdate,
} from "../data/patient-profile";
import {
  bodyOf,
  fail,
  isoFromNow,
  uid,
  type Ctx,
  type Permission,
  type Reply,
  type Router,
  type Schemas,
  type Session,
} from "../core";
import { USERS } from "../auth";

type S = Schemas;

const SOURCES = [
  "doctor_recommendation",
  "service_protocol",
  "treatment_plan",
  "followup_automation",
];
const FINANCE: readonly Permission[] = ["finance.read", "finance.collect", "finance.write"];
const OPEN_VISIT = ["booked", "confirmed", "arrived", "in_progress"];

/** Recommended return dates saved from the dialog, by patient id. */
const expectedOverrides: Record<string, { date: string; reason: string; source: string }> = {};

function session(ctx: Ctx): Session {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

const nameOf = (userId: string): string | null =>
  USERS.find((u) => u.id === userId)?.display_name ?? null;

function patientOr404(ctx: Ctx): S["PatientOut"] {
  const found = patientById(ctx.params.patient_id ?? "");
  if (!found) fail(404, "not_found", "Không tìm thấy bệnh nhân.");
  return found;
}

function holds(s: Session | null, ...permissions: readonly Permission[]): boolean {
  return s !== null && permissions.some((p) => s.permissions.includes(p));
}

function invalid(message: string): never {
  return fail(422, "validation_failed", message);
}

const today = (): string => isoFromNow(0).slice(0, 10);
const day = (iso: string): string => {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d}/${m}/${y}`;
};

// ------------------------------------------------------------------------------- views used by clinic.ts

/** The chip of `/patients` (`?view=`). */
export function matchesView(patient: S["PatientOut"], view: string | null): boolean {
  if (view === null || view === "all") return true;
  if (view === "alerts") return (alertsByPatient[patient.id] ?? []).length > 0;
  if (view === "active")
    return plans.some(
      (p) =>
        p.patient_id === patient.id &&
        (p.status === "active" || p.status === "planned") &&
        p.completed_sessions < p.total_sessions,
    );
  if (view === "next") {
    const from = today();
    const to = isoFromNow(7 * 86_400_000).slice(0, 10);
    return appointments.some(
      (a) =>
        a.patient_id === patient.id &&
        OPEN_VISIT.includes(a.status) &&
        a.starts_at.slice(0, 10) >= from &&
        a.starts_at.slice(0, 10) <= to,
    );
  }
  return true;
}

/** What the 360 adds in U9: the warning lines, the saved return date, the price of a course only for finance. */
export function decorate360(card: S["Patient360"], viewer: Session | null): S["Patient360"] {
  const id = card.patient.id;
  const money = holds(viewer, ...FINANCE);
  const override = expectedOverrides[id];
  const hasBooking = card.profile.expected_visit_source === "appointment";
  return {
    ...card,
    alerts: alertsByPatient[id] ?? [],
    plans: (card.plans ?? []).map((p) =>
      money
        ? p
        : {
            ...p,
            unit_price_vnd: null,
            discount_vnd: null,
            agreed_price_vnd: null,
            service_terms_version: null,
          },
    ),
    profile:
      override && !hasBooking
        ? {
            ...card.profile,
            expected_next_visit_at: override.date,
            expected_visit_source: override.source,
          }
        : card.profile,
  };
}

// ----------------------------------------------------------------------------------------------- brief

function buildBrief(patient: S["PatientOut"]): { text: string; source_ids: string[] } {
  const sources: string[] = [];
  const own = plans.filter((p) => p.patient_id === patient.id);
  const lead = own.find((p) => p.completed_sessions < p.total_sessions) ?? own.at(0);
  const last = sessionsOf(patient.id).find((s) => s.status === "completed");
  const next = appointments
    .filter((a) => a.patient_id === patient.id && OPEN_VISIT.includes(a.status))
    .filter((a) => a.starts_at.slice(0, 10) >= today())
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at))
    .at(0);
  const open = tasks.filter(
    (t) => t.patient_id === patient.id && (t.status === "open" || t.status === "rescheduled"),
  );
  const parts = [`${patient.full_name}.`];
  if (lead) {
    sources.push(`plan:${lead.id}`);
    parts.push(
      `Liệu trình ${lead.title}: đã hoàn tất ${lead.completed_sessions}/${lead.total_sessions} buổi.`,
    );
  } else {
    parts.push("Chưa có liệu trình được thiết lập.");
  }
  if (last) {
    sources.push(`session:${last.id}`);
    parts.push(`Lần gần nhất: ${day(last.performed_at)}.`, `Buổi gần nhất: ${last.title}.`);
  } else {
    parts.push("Lần gần nhất: Chưa ghi nhận.", "Chưa có cập nhật sau điều trị.");
  }
  if (next) {
    sources.push(`appointment:${next.id}`);
    parts.push(`Hẹn tiếp theo: ${day(next.starts_at)}.`);
  } else {
    parts.push("Chưa có lịch hẹn tiếp theo.");
  }
  const alerts = alertsByPatient[patient.id] ?? [];
  if (alerts.length > 0) parts.push(`Cần nhớ: ${alerts.join("; ")}.`);
  if (open.length > 0) {
    open.forEach((t) => sources.push(`crm_task:${t.id}`));
    parts.push(`Có ${open.length} mục theo dõi chưa xử lý; cần kiểm tra trước buổi tiếp theo.`);
  } else {
    parts.push("Không có mục theo dõi đang mở.");
  }
  parts.push("Bước tiếp theo: bác sĩ đánh giá đáp ứng, xác nhận dữ liệu và quyết định kế hoạch.");
  return { text: parts.join(" "), source_ids: sources };
}

function lastApproved(patientId: string): S["BriefApprovedOut"] | null {
  const row = briefs.filter((b) => b.patient_id === patientId).at(-1);
  if (!row) return null;
  const { patient_id: _patient, ...out } = row;
  return out;
}

// -------------------------------------------------------------------------------------------- register

function updateOut(row: StoredAppUpdate): S["AppUpdateOut"] {
  const { patient_id: _patient, ...out } = row;
  return out;
}

export function register(r: Router): void {
  r.put("/api/v1/patients/{patient_id}/alerts", "session.write", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const input = bodyOf<S["AlertsUpdate"]>(ctx);
    const lines = input.alerts
      .flatMap((entry) => entry.split("\n"))
      .map((line) => line.trim())
      .filter((line) => line !== "");
    if (lines.length > 20) invalid("Tối đa 20 cảnh báo.");
    if (lines.some((line) => line.length > 200)) invalid("Mỗi cảnh báo tối đa 200 ký tự.");
    alertsByPatient[patient.id] = lines;
    return { body: { alerts: lines } };
  });

  r.get("/api/v1/patients/{patient_id}/clinical-note", "session.read", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const row = clinicalNotes.find((n) => n.patient_id === patient.id);
    if (!row)
      return { body: { history: "", diagnosis: "", reviewed_by_name: null, reviewed_at: null } };
    const { patient_id: _patient, ...out } = row;
    return { body: out };
  });
  r.put("/api/v1/patients/{patient_id}/clinical-note", "session.write", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const input = bodyOf<S["ClinicalNoteUpdate"]>(ctx);
    if (input.history.trim() === "" || input.diagnosis.trim() === "")
      invalid("Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận.");
    const saved = {
      patient_id: patient.id,
      history: input.history.trim(),
      diagnosis: input.diagnosis.trim(),
      reviewed_by_name: nameOf(session(ctx).userId),
      reviewed_at: isoFromNow(0),
    };
    const at = clinicalNotes.findIndex((n) => n.patient_id === patient.id);
    if (at >= 0) clinicalNotes[at] = saved;
    else clinicalNotes.push(saved);
    const { patient_id: _patient, ...out } = saved;
    return { body: out };
  });

  r.put("/api/v1/patients/{patient_id}/expected-return", "crm.activity.write", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const input = bodyOf<S["ExpectedReturnUpdate"]>(ctx);
    const real =
      /^\d{4}-\d{2}-\d{2}$/.test(input.date) &&
      new Date(`${input.date}T00:00:00Z`).toISOString().slice(0, 10) === input.date;
    if (!real || input.reason.trim() === "" || !SOURCES.includes(input.source))
      invalid("Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.");
    expectedOverrides[patient.id] = {
      date: input.date,
      reason: input.reason.trim(),
      source: input.source,
    };
    return { body: { date: input.date, reason: input.reason.trim(), source: input.source } };
  });

  r.get("/api/v1/patients/{patient_id}/app-updates", "session.read", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const kind = ctx.query.get("kind");
    return {
      body: appUpdates
        .filter((u) => u.patient_id === patient.id && (kind === null || u.kind === kind))
        .toSorted((a, b) => b.created_at.localeCompare(a.created_at))
        .map(updateOut),
    };
  });
  r.post("/api/v1/patients/{patient_id}/app-updates", null, (ctx): Reply => {
    const patient = patientOr404(ctx);
    const user = session(ctx);
    const input = bodyOf<S["AppUpdateCreate"]>(ctx);
    const needs: Permission = input.kind === "aftercare" ? "session.write" : "conversation.reply";
    if (!holds(user, needs)) fail(403, "forbidden", "Bạn không có quyền thực hiện thao tác này.");
    if (input.body.trim() === "")
      invalid(input.kind === "aftercare" ? "Hãy nhập hướng dẫn." : "Hãy nhập nội dung tin nhắn.");
    const row: StoredAppUpdate = {
      id: uid("appupd"),
      patient_id: patient.id,
      kind: input.kind,
      body: input.body.trim(),
      created_at: isoFromNow(0),
      by_name: nameOf(user.userId),
    };
    appUpdates.push(row);
    return { status: 201, body: updateOut(row) };
  });

  r.get("/api/v1/patients/{patient_id}/brief", "session.write", (ctx): Reply => {
    const patient = patientOr404(ctx);
    return { body: { ...buildBrief(patient), approved: lastApproved(patient.id) } };
  });
  r.post("/api/v1/patients/{patient_id}/brief/approve", "session.write", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const input = bodyOf<S["BriefApprove"]>(ctx);
    if (input.text.trim() === "") invalid("Brief không được để trống.");
    const row = {
      patient_id: patient.id,
      id: uid("brief"),
      text: input.text.trim(),
      approved_by_name: nameOf(session(ctx).userId),
      approved_at: isoFromNow(0),
      source_ids: buildBrief(patient).source_ids,
    };
    briefs.push(row);
    const { patient_id: _patient, ...out } = row;
    return { status: 201, body: out };
  });

  r.get("/api/v1/patients/{patient_id}/finance-tab", "finance.read", (ctx): Reply => {
    const patient = patientOr404(ctx);
    return {
      body: {
        patient,
        plans: plans
          .filter((p) => p.patient_id === patient.id)
          .map(({ patient_id: _patient, ...plan }) => plan),
      },
    };
  });

  r.post("/api/v1/patients/{patient_id}/service-plans", "finance.write", (ctx): Reply => {
    const patient = patientOr404(ctx);
    const input = bodyOf<S["ServicePlanCreate"]>(ctx);
    const service = services.find((s) => s.id === input.service_id);
    if (!service) fail(404, "not_found", "Không tìm thấy dịch vụ.");
    if (!service.active) invalid("Dịch vụ đã ngừng dùng, chưa thể thêm vào liệu trình.");
    if (!Number.isInteger(input.sessions) || input.sessions < 1 || input.sessions > 20)
      invalid("Số buổi từ 1 đến 20.");
    const terms = service.history.find((t) => t.version_no === service.terms_version);
    const unit = terms?.price_vnd ?? 0;
    const discount = input.discount_vnd ?? 0;
    if (discount < 0 || discount > unit * input.sessions)
      invalid("Giảm giá không được vượt quá giá niêm yết của liệu trình.");
    const created = {
      id: uid("plan"),
      patient_id: patient.id,
      episode_id: null,
      service_code: service.code,
      title: service.name,
      goal: null,
      total_sessions: input.sessions,
      completed_sessions: 0,
      status: "active",
      doctor_id: patient.doctor_id ?? null,
      version: 1,
      unit_price_vnd: unit,
      discount_vnd: discount,
      agreed_price_vnd: unit * input.sessions - discount,
      service_terms_version: service.terms_version,
    };
    plans.push(created);
    const { patient_id: _patient, ...plan } = created;
    return { status: 201, body: plan };
  });
}
