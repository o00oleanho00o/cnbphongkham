// Mock of the clinic operations API: patients (+360), consents, appointments, CRM tasks and activities,
// conversations (Inbox) and the review queue. State lives in module variables (see mock/data/clinic.ts).
import { foldForSearch } from "../../src/lib/admin/shared/fold-for-search";
import {
  DOCTOR_NAMES,
  activities,
  appointments,
  clinicToday,
  consents,
  conversations,
  messages,
  patientById,
  patients,
  reviewItems,
  tasks,
} from "../data/clinic";
import {
  HttpError,
  bodyOf,
  fail,
  isoFromNow,
  paginate,
  uid,
  uuid,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
  type Session,
} from "../core";
import { lightSession, notes, plansOf, sessionsOf } from "../data/patient-care";
import { assertAssignable } from "../assignable";
import { viewersFor } from "../live-bus";

type S = Schemas;

const VERSION_CONFLICT = "Bản ghi vừa được người khác cập nhật. Tải lại rồi thử lại.";

function session(ctx: Ctx): Session {
  if (!ctx.session) throw new HttpError(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

function checkVersion(current: number, sent: number): void {
  if (current !== sent) fail(409, "version_conflict", VERSION_CONFLICT);
}

const MINUTE_MS = 60_000;

const idempotent = new Map<string, unknown>();

/** Same key, same answer: what the BE does for approve / resolve / reply. */
function once<T>(ctx: Ctx, scope: string, produce: () => T): T {
  const key = ctx.req.headers["idempotency-key"];
  if (typeof key !== "string") return produce();
  const cacheKey = `${scope}:${key}`;
  if (idempotent.has(cacheKey)) return idempotent.get(cacheKey) as T;
  const result = produce();
  idempotent.set(cacheKey, result);
  return result;
}

function findOr404<T extends { id: string }>(items: T[], id: string, what: string): T {
  const found = items.find((item) => item.id === id);
  if (!found) fail(404, "not_found", `Không tìm thấy ${what}.`);
  return found;
}

// ----------------------------------------------------------------- patients

function matchesQuery(p: S["PatientOut"], q: string): boolean {
  const needle = foldForSearch(q);
  return foldForSearch(`${p.full_name} ${p.code}`).includes(needle);
}

function patient360(p: S["PatientOut"]): S["Patient360"] {
  const patientAppointments = appointments.filter((a) => a.patient_id === p.id);
  const openTasks = tasks.filter(
    (t) => t.patient_id === p.id && (t.status === "open" || t.status === "rescheduled"),
  );
  const lastVisit = patientAppointments
    .filter((a) => a.status === "completed")
    .toSorted((a, b) => b.starts_at.localeCompare(a.starts_at))[0];
  const next = patientAppointments
    .filter((a) => a.status === "booked" || a.status === "confirmed")
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
  const isTreating = p.code === "P001" || p.code === "P007";
  return {
    patient: p,
    profile: {
      lifecycle_stage: isTreating ? "treating" : "returning",
      last_visit_at: lastVisit?.starts_at.slice(0, 10) ?? null,
      expected_next_visit_at: next?.starts_at.slice(0, 10) ?? null,
      expected_visit_source: next ? "appointment" : "doctor_recommendation",
      overdue_days: p.code === "P005" ? 2 : 0,
      remaining_sessions: isTreating ? 2 : 0,
      risk_level: p.code === "P005" || p.code === "P006" ? "high" : "normal",
      marketing_opt_out: p.marketing_opt_out ?? false,
    },
    appointments: patientAppointments,
    open_tasks: openTasks,
    consents: consents[p.id] ?? [],
    conversations: conversations
      .filter((c) => c.patient_id === p.id)
      .map(({ created_at: _created, ...summary }) => summary),
    episodes: isTreating
      ? [
          {
            id: uuid(1, 12),
            title: "Điều trị nám và phục hồi da",
            status: "active",
            started_on: isoFromNow(-60 * 86_400_000).slice(0, 10),
            closed_on: null,
          },
        ]
      : [],
    plans: plansOf(p.id),
    recent_sessions: sessionsOf(p.id).slice(0, 10).map(lightSession),
    recent_activities: activities.filter((a) => a.patient_id === p.id),
    timeline: [
      ...patientAppointments.map((a) => ({
        id: `a-${a.id}`,
        at: a.starts_at,
        kind: "appointment",
        title: a.note ?? "Lịch hẹn",
        detail: a.status,
        by: null,
        source_id: a.id,
      })),
      ...activities
        .filter((a) => a.patient_id === p.id)
        .map((a) => ({
          id: `c-${a.id}`,
          at: a.occurred_at,
          kind: "crm_activity",
          title: "Liên hệ chăm sóc",
          detail: a.note,
          by: a.actor_name ?? null,
          source_id: a.id,
        })),
      ...notes
        .filter((n) => n.patient_id === p.id && n.status === "approved" && n.approved_at)
        .map((n) => ({
          id: `consult-${n.id}`,
          at: n.approved_at ?? n.created_at,
          kind: "consult",
          title: "Ghi chú tư vấn đã được duyệt",
          detail: null,
          by: n.approved_by_name ?? null,
          source_id: n.id,
        })),
    ].toSorted((a, b) => b.at.localeCompare(a.at)),
  };
}

// -------------------------------------------------------------- appointments

const TRANSITIONS: Record<string, { from: S["AppointmentStatus"][]; to: S["AppointmentStatus"] }> =
  {
    confirm: { from: ["booked"], to: "confirmed" },
    "check-in": { from: ["booked", "confirmed"], to: "arrived" },
    start: { from: ["arrived"], to: "in_progress" },
    complete: { from: ["in_progress"], to: "completed" },
    miss: { from: ["booked", "confirmed"], to: "missed" },
    cancel: { from: ["booked", "confirmed", "arrived"], to: "cancelled" },
  };

function transitionRoute(name: string) {
  return (ctx: Ctx): Reply => {
    const appt = findOr404(appointments, ctx.params.appointment_id ?? "", "lịch hẹn");
    const { version, reason } = bodyOf<S["AppointmentTransition"]>(ctx);
    checkVersion(appt.version, version);
    const rule = TRANSITIONS[name];
    if (!rule || !rule.from.includes(appt.status)) {
      fail(409, "invalid_state", "Lịch hẹn không ở trạng thái cho phép thao tác này.");
    }
    appt.status = rule.to;
    appt.version += 1;
    if (name === "cancel") {
      appt.cancel_reason = reason ?? null;
      appt.cancelled_at = isoFromNow(0);
    }
    return { body: appt };
  };
}

const WORK_START = 8 * 60;
const WORK_END = 18 * 60;
const BREAK_START = 12 * 60;
const BREAK_END = 13 * 60;
const FREE: readonly S["AppointmentStatus"][] = ["cancelled", "missed"];

/** Minutes after midnight, clinic time, of an ISO string with the +07:00 offset. */
function clinicMinutes(iso: string): number {
  const hh = Number.parseInt(iso.slice(11, 13), 10);
  const mm = Number.parseInt(iso.slice(14, 16), 10);
  return hh * 60 + mm;
}

/** The BE's hours rule (08:00-18:00, break 12:00-13:00), same sentences. */
function slotProblem(startsAt: string, duration: number): string | null {
  const start = clinicMinutes(startsAt);
  const end = start + duration;
  if (startsAt.slice(0, 10) < clinicToday()) return "Ngày giờ hẹn phải từ hiện tại trở đi.";
  if (end > 24 * 60) return "Lịch hẹn không được kéo dài sang ngày khác.";
  if (start < WORK_START || end > WORK_END) return "Ngoài ca làm việc 08:00–18:00 của phòng khám.";
  if (start < BREAK_END && end > BREAK_START) return "Trùng giờ nghỉ 12:00–13:00.";
  return null;
}

/** Who the candidate collides with on this appointment (patient first, like the BE), or null. */
function clashWith(a: S["AppointmentOut"], patientId: string, doctorId: string | null) {
  if (a.patient_id === patientId) return "bệnh nhân";
  return doctorId !== null && a.doctor_id === doctorId ? "bác sĩ" : null;
}

/** The BE's double-booking sentence, or null: same doctor or same patient on an overlapping slot. */
function findClash(
  patientId: string,
  doctorId: string | null,
  startMs: number,
  duration: number,
  ignoreId: string | null,
): string | null {
  const endMs = startMs + duration * MINUTE_MS;
  const overlapping = appointments.filter((a) => {
    if (a.id === ignoreId || FREE.includes(a.status)) return false;
    const aStart = Date.parse(a.starts_at);
    return startMs < aStart + a.duration_min * MINUTE_MS && endMs > aStart;
  });
  const hit = overlapping
    .map((a) => ({ a, who: clashWith(a, patientId, doctorId) }))
    .find((candidate) => candidate.who !== null);
  if (!hit) return null;
  const at = hit.a.starts_at;
  return `Trùng lịch của ${hit.who} lúc ${at.slice(8, 10)}/${at.slice(5, 7)} ${at.slice(11, 16)}.`;
}

function createAppointment(input: S["AppointmentCreate"], by: string): S["AppointmentOut"] {
  const p = patientById(input.patient_id);
  if (!p) fail(404, "not_found", "Không tìm thấy bệnh nhân.");
  const doctorId = input.doctor_id ?? p.doctor_id ?? null;
  const duration = input.duration_min ?? 45;
  const problem = slotProblem(input.starts_at, duration);
  if (problem) fail(422, "validation_failed", problem);
  const clash = findClash(p.id, doctorId, Date.parse(input.starts_at), duration, null);
  if (clash) fail(409, "appointment_conflict", clash);
  const created: S["AppointmentOut"] = {
    id: uid("appt"),
    patient_id: p.id,
    patient_code: p.code,
    doctor_id: input.doctor_id ?? p.doctor_id ?? null,
    starts_at: input.starts_at,
    duration_min: input.duration_min ?? 45,
    status: "booked",
    note: input.note ?? null,
    created_by: by,
    cancel_reason: null,
    cancelled_at: null,
    missed_at: null,
    version: 1,
  };
  appointments.push(created);
  return created;
}

// ---------------------------------------------------------- board and KPIs

const DAY_MS = 86_400_000;
const DAY_KEY = /^\d{4}-\d{2}-\d{2}$/;

function dayStartMs(day: string): number {
  return Date.parse(`${day}T00:00:00+07:00`);
}

function addDaysKey(day: string, n: number): string {
  return new Date(dayStartMs(day) + n * DAY_MS + 7 * 3_600_000).toISOString().slice(0, 10);
}

function validDay(value: string | null): string {
  if (value === null || !DAY_KEY.test(value) || Number.isNaN(dayStartMs(value))) {
    fail(422, "validation_failed", "Dữ liệu gửi lên không hợp lệ.");
  }
  return value;
}

/** `GET /appointments/schedule`: the day or the 7 days, a doctor only their own (like the BE). */
function scheduleRoute(ctx: Ctx): Reply {
  const user = session(ctx);
  const day = validDay(ctx.query.get("day"));
  const view: S["ScheduleView"] = ctx.query.get("view") === "week" ? "week" : "day";
  const days = view === "week" ? 7 : 1;
  const own = user.role === "doctor";
  const wanted = own ? user.userId : ctx.query.get("doctor_id");
  const from = dayStartMs(day);
  const to = from + days * DAY_MS;
  const names = user.permissions.includes("patient.read");
  const items: S["ScheduleItem"][] = appointments
    .filter((a) => {
      const at = Date.parse(a.starts_at);
      return at >= from && at < to && (!wanted || a.doctor_id === wanted);
    })
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at))
    .map((a) => ({
      ...a,
      patient_name: names ? (patientById(a.patient_id)?.full_name ?? null) : null,
      doctor_name: a.doctor_id ? (DOCTOR_NAMES[a.doctor_id] ?? null) : null,
    }));
  const doctors = Object.entries(DOCTOR_NAMES)
    .filter(([id]) => !own || id === user.userId)
    .map(([id, name]) => ({ id, name }))
    .toSorted((a, b) => a.name.localeCompare(b.name, "vi"));
  return {
    body: {
      view,
      from_day: day,
      to_day: addDaysKey(day, days - 1),
      doctor_id: wanted ?? null,
      items,
      doctors,
    } satisfies S["ScheduleOut"],
  };
}

/** `GET /appointments/free-slot`: first start (steps of 15 minutes from 08:00) the rules accept. */
function freeSlotRoute(ctx: Ctx): Reply {
  const day = validDay(ctx.query.get("day"));
  const patientId = ctx.query.get("patient_id") ?? "";
  if (!patientById(patientId)) fail(404, "not_found", "Không tìm thấy bệnh nhân.");
  const doctorId = ctx.query.get("doctor_id");
  const duration = Number.parseInt(ctx.query.get("duration_min") ?? "30", 10);
  const steps = Math.max(0, Math.floor((WORK_END - WORK_START - duration) / 15) + 1);
  const free = Array.from({ length: steps }, (_, i) => WORK_START + i * 15)
    .map((minute) => {
      const hh = String(Math.floor(minute / 60)).padStart(2, "0");
      const mm = String(minute % 60).padStart(2, "0");
      return `${day}T${hh}:${mm}:00+07:00`;
    })
    .find(
      (startsAt) =>
        slotProblem(startsAt, duration) === null &&
        Date.parse(startsAt) > Date.now() &&
        findClash(patientId, doctorId, Date.parse(startsAt), duration, null) === null,
    );
  return { body: { starts_at: free ?? null } satisfies S["FreeSlotOut"] };
}

function rangeOf(range: S["DashboardRange"]): [string, string] {
  const today = clinicToday();
  if (range === "today") return [today, today];
  const weekday = (new Date(dayStartMs(today) + 7 * 3_600_000).getUTCDay() + 6) % 7;
  if (range === "week") return [addDaysKey(today, -weekday), addDaysKey(today, 6 - weekday)];
  const first = `${today.slice(0, 8)}01`;
  const next = addDaysKey(`${today.slice(0, 8)}28`, 4);
  return [first, addDaysKey(`${next.slice(0, 8)}01`, -1)];
}

const pct = (part: number, whole: number): number | null =>
  whole === 0 ? null : Math.round((part * 100) / whole);

type Window = { from: number; to: number };

function appointmentKpis(
  user: Session,
  window: Window,
): { appointments: S["AppointmentKpis"]; patients: S["PatientKpis"] } {
  const inRange = appointments.filter((a) => {
    const at = Date.parse(a.starts_at);
    return (
      at >= window.from && at < window.to && (user.role !== "doctor" || a.doctor_id === user.userId)
    );
  });
  const count = (...statuses: S["AppointmentStatus"][]) =>
    inRange.filter((a) => statuses.includes(a.status)).length;
  const visited = inRange.filter((a) => ["arrived", "in_progress", "completed"].includes(a.status));
  const seen = new Set(visited.map((a) => a.patient_id)).size;
  return {
    appointments: {
      total: inRange.length,
      upcoming: count("booked", "confirmed"),
      waiting: count("arrived"),
      in_progress: count("in_progress"),
      completed: count("completed"),
      missed: count("missed"),
      cancelled: count("cancelled"),
      visits: visited.length,
    },
    // the mock patients carry no first-contact date: every patient seen counts as returning
    patients: { seen, new: 0, returning: seen },
  };
}

function careKpis(window: Window): S["CareKpis"] {
  const today = dayStartMs(clinicToday());
  const isOpen = (t: S["CrmTaskOut"]) => t.status === "open" || t.status === "rescheduled";
  const due = tasks.filter((t) => {
    const at = Date.parse(t.due_at);
    return at >= window.from && at < window.to && (isOpen(t) || t.status === "resolved");
  });
  const resolved = due.filter((t) => t.status === "resolved").length;
  const overdue = tasks.filter((t) => isOpen(t) && Date.parse(t.due_at) < today);
  const contacts = activities.filter((a) => {
    const at = Date.parse(a.occurred_at);
    return at >= window.from && at < window.to && a.channel !== "internal_note";
  });
  const reached = contacts.filter((a) => a.outcome !== "unanswered" && a.outcome !== "invalid");
  return {
    tasks_due: due.length,
    tasks_resolved: resolved,
    followup_completion_pct: pct(resolved, due.length),
    overdue_tasks: overdue.length,
    overdue_patients: new Set(overdue.map((t) => t.patient_id)).size,
    contact_attempts: contacts.length,
    contacts_reached: reached.length,
    contact_rate_pct: pct(reached.length, contacts.length),
    booked_after_care: contacts.filter((a) => a.related_appointment_id !== null).length,
  };
}

/** `GET /dashboard/kpis`: the same numbers the BE computes, from the mock rows. No money. */
function kpisRoute(ctx: Ctx): Reply {
  const user = session(ctx);
  const raw = ctx.query.get("range") ?? "today";
  if (raw !== "today" && raw !== "week" && raw !== "month") {
    fail(422, "validation_failed", "Dữ liệu gửi lên không hợp lệ.");
  }
  const range: S["DashboardRange"] = raw;
  const [first, last] = rangeOf(range);
  const window: Window = { from: dayStartMs(first), to: dayStartMs(last) + DAY_MS };
  const canAppointments = user.permissions.includes("appointment.read");
  const canCare = user.permissions.includes("crm.task.read");
  if (!canAppointments && !canCare) fail(403, "forbidden", "Bạn không có quyền xem tổng quan.");

  const operating = canAppointments ? appointmentKpis(user, window) : null;
  return {
    body: {
      range,
      scope: user.role === "doctor" ? "doctor" : "clinic",
      starts_on: first,
      ends_on: last,
      appointments: operating?.appointments ?? null,
      patients: operating?.patients ?? null,
      care: canCare ? careKpis(window) : null,
    } satisfies S["DashboardKpisOut"],
  };
}

// ------------------------------------------------------------------- tasks

function resolveTask(ctx: Ctx): Reply {
  const user = session(ctx);
  const task = findOr404(tasks, ctx.params.task_id ?? "", "việc chăm sóc");
  const input = bodyOf<S["CrmTaskResolve"]>(ctx);
  return once(ctx, `resolve:${task.id}`, (): Reply => {
    checkVersion(task.version, input.version);
    if (task.status !== "open" && task.status !== "rescheduled") {
      fail(409, "invalid_state", "Việc đã được xử lý hoặc không còn hợp lệ. Tải lại danh sách.");
    }
    if (!input.note.trim()) fail(422, "validation_failed", "Nhập ghi chú kết quả liên hệ.");
    if (input.outcome === "booked" && !input.booking) {
      fail(422, "validation_failed", "Cần lưu lịch hẹn hợp lệ trước khi hoàn tất việc.");
    }
    assertAssignable(input.owner_user_id, "Chọn người phụ trách hợp lệ.");
    const appointment = input.booking ? createAppointment(input.booking, user.userId) : null;
    activities.unshift({
      id: uid("act"),
      patient_id: task.patient_id,
      task_id: task.id,
      kind: "contact",
      channel: input.channel,
      outcome: input.outcome,
      note: input.note,
      actor_user_id: user.userId,
      actor_name: null,
      occurred_at: isoFromNow(0),
      next_action_at: input.next_action_at ?? null,
      related_appointment_id: appointment?.id ?? null,
    });
    const reschedule = input.next_action_at && !appointment;
    task.status = reschedule ? "rescheduled" : "resolved";
    task.resolution = input.outcome;
    task.resolved_at = reschedule ? null : isoFromNow(0);
    task.owner_user_id = input.owner_user_id;
    task.priority = input.priority ?? task.priority;
    task.related_appointment_id = appointment?.id ?? null;
    if (input.next_action_at && reschedule) task.due_at = input.next_action_at;
    task.version += 1;
    if (input.outcome === "optout") {
      const p = patientById(task.patient_id);
      if (p) p.marketing_opt_out = true;
    }
    return { body: task };
  });
}

// ------------------------------------------------------------ conversations

function conversationSummary(c: S["ConversationOut"]): S["ConversationSummary"] {
  const { created_at: _created, ...summary } = c;
  return summary;
}

function sendStaffMessage(ctx: Ctx): Reply {
  const user = session(ctx);
  const conv = findOr404(conversations, ctx.params.conversation_id ?? "", "hội thoại");
  const { text, proactive } = bodyOf<S["MessageCreate"]>(ctx);
  return once(ctx, `msg:${conv.id}`, (): Reply => {
    if (!text.trim()) fail(422, "validation_failed", "Nhập nội dung tin nhắn.");
    if (conv.status === "closed") {
      fail(409, "invalid_state", "Hội thoại đã đóng. Mở lại trước khi nhắn.");
    }
    const created: S["MessageOut"] = {
      id: uid("msg"),
      conversation_id: conv.id,
      direction: "outbound",
      sender_type: "staff",
      sender_user_id: user.userId,
      body: text.trim(),
      status: "sent",
      created_at: isoFromNow(0),
      sent_at: isoFromNow(0),
      proactive: proactive ?? false,
      review_item_id: null,
      error_code: null,
    };
    messages.push(created);
    conv.last_message_at = created.created_at;
    conv.last_message_preview = created.body;
    conv.unread_count = 0;
    conv.version += 1;
    return { status: 201, body: created };
  });
}

// ------------------------------------------------------------------- review

function decideGuard(ctx: Ctx, item: S["ReviewItemOut"]): void {
  const user = session(ctx);
  if (item.status !== "pending" && item.status !== "escalated") {
    fail(409, "invalid_state", "Mục này đã được xử lý.");
  }
  if (item.requires_doctor && !user.permissions.includes("review.decide_clinical")) {
    fail(403, "forbidden", "Nội dung liên quan lâm sàng: cần bác sĩ duyệt.");
  }
}

function closeLinkedConversation(item: S["ReviewItemOut"]): void {
  const conv = conversations.find((c) => c.id === item.conversation_id);
  if (!conv) return;
  const stillPending = reviewItems.some(
    (r) => r.conversation_id === conv.id && r.id !== item.id && r.status === "pending",
  );
  conv.has_pending_review = stillPending;
  if (!stillPending && conv.status === "pending_review") conv.status = "open";
}

export function register(r: Router): void {
  // patients
  r.get("/api/v1/patients", "patient.read", (ctx): Reply => {
    const q = ctx.query.get("q");
    const doctor = ctx.query.get("doctor_id");
    const owner = ctx.query.get("cs_owner_id");
    const found = patients
      .filter((p) => !q || matchesQuery(p, q))
      .filter((p) => !doctor || p.doctor_id === doctor)
      .filter((p) => !owner || p.cs_owner_id === owner);
    return { body: paginate(found, ctx.query) };
  });
  r.post("/api/v1/patients", "patient.write", (ctx): Reply => {
    const input = bodyOf<S["PatientCreate"]>(ctx);
    const n = patients.length + 1;
    const created: S["PatientOut"] = {
      id: uuid(n, 2),
      code: input.code ?? `P${String(n).padStart(3, "0")}`,
      full_name: input.full_name,
      gender: input.gender ?? "unknown",
      birth_date: input.birth_date ?? null,
      doctor_id: input.doctor_id ?? null,
      cs_owner_id: input.cs_owner_id ?? null,
      phone: input.phone ?? null,
      source: input.source ?? null,
      marketing_opt_out: false,
      version: 1,
    };
    patients.push(created);
    return { status: 201, body: created };
  });
  r.get("/api/v1/patients/{patient_id}", "patient.read", (ctx): Reply => ({
    body: findOr404(patients, ctx.params.patient_id ?? "", "bệnh nhân"),
  }));
  r.patch("/api/v1/patients/{patient_id}", "patient.write", (ctx): Reply => {
    const p = findOr404(patients, ctx.params.patient_id ?? "", "bệnh nhân");
    const { version, ...patch } = bodyOf<S["PatientUpdate"]>(ctx);
    checkVersion(p.version, version);
    const cleaned = Object.fromEntries(
      Object.entries(patch).filter(([, v]) => v !== undefined && v !== null),
    );
    Object.assign(p, cleaned, { version: p.version + 1 });
    return { body: p };
  });
  r.get("/api/v1/patients/{patient_id}/360", "patient.read_360", (ctx): Reply => ({
    body: patient360(findOr404(patients, ctx.params.patient_id ?? "", "bệnh nhân")),
  }));
  r.get("/api/v1/patients/{patient_id}/consents", "consent.read", (ctx): Reply => {
    const p = findOr404(patients, ctx.params.patient_id ?? "", "bệnh nhân");
    return { body: consents[p.id] ?? [] };
  });
  r.post("/api/v1/patients/{patient_id}/consents", "consent.write", (ctx): Reply => {
    const p = findOr404(patients, ctx.params.patient_id ?? "", "bệnh nhân");
    const input = bodyOf<S["ConsentCreate"]>(ctx);
    const created: S["ConsentOut"] = {
      id: uid("consent"),
      kind: input.kind,
      granted: input.granted,
      granted_at: input.granted ? isoFromNow(0) : null,
      revoked_at: input.granted ? null : isoFromNow(0),
      source: input.source ?? null,
    };
    consents[p.id] = [...(consents[p.id] ?? []).filter((c) => c.kind !== input.kind), created];
    return { status: 201, body: created };
  });

  // appointments
  r.get("/api/v1/appointments", "appointment.read", (ctx): Reply => {
    const patient = ctx.query.get("patient_id");
    const doctor = ctx.query.get("doctor_id");
    const status = ctx.query.get("appointment_status");
    const from = ctx.query.get("starts_from");
    const to = ctx.query.get("starts_to");
    const found = appointments
      .filter((a) => !patient || a.patient_id === patient)
      .filter((a) => !doctor || a.doctor_id === doctor)
      .filter((a) => !status || a.status === status)
      .filter((a) => !from || a.starts_at >= from)
      .filter((a) => !to || a.starts_at <= to)
      .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at));
    return { body: paginate(found, ctx.query) };
  });
  r.get("/api/v1/appointments/schedule", "appointment.read", scheduleRoute);
  r.get("/api/v1/appointments/free-slot", "appointment.write", freeSlotRoute);
  r.post("/api/v1/appointments", "appointment.write", (ctx): Reply => ({
    status: 201,
    body: createAppointment(bodyOf<S["AppointmentCreate"]>(ctx), session(ctx).userId),
  }));
  r.get("/api/v1/appointments/{appointment_id}", "appointment.read", (ctx): Reply => ({
    body: findOr404(appointments, ctx.params.appointment_id ?? "", "lịch hẹn"),
  }));
  r.patch("/api/v1/appointments/{appointment_id}", "appointment.write", (ctx): Reply => {
    const appt = findOr404(appointments, ctx.params.appointment_id ?? "", "lịch hẹn");
    const { version, ...patch } = bodyOf<S["AppointmentUpdate"]>(ctx);
    checkVersion(appt.version, version);
    if (appt.status !== "booked" && appt.status !== "confirmed") {
      fail(409, "invalid_state", "Lịch đã bắt đầu, hoàn tất, hủy hoặc vắng; hãy tạo lịch mới.");
    }
    const cleaned = Object.fromEntries(
      Object.entries(patch).filter(([, v]) => v !== undefined && v !== null),
    ) as Partial<S["AppointmentOut"]>;
    const startsAt = cleaned.starts_at ?? appt.starts_at;
    const duration = cleaned.duration_min ?? appt.duration_min;
    const doctorId = "doctor_id" in patch ? (patch.doctor_id ?? null) : appt.doctor_id;
    const problem = slotProblem(startsAt, duration);
    if (problem) fail(422, "validation_failed", problem);
    const clash = findClash(appt.patient_id, doctorId, Date.parse(startsAt), duration, appt.id);
    if (clash) fail(409, "appointment_conflict", clash);
    Object.assign(appt, cleaned, { doctor_id: doctorId, version: appt.version + 1 });
    return { body: appt };
  });
  r.post(
    "/api/v1/appointments/{appointment_id}/confirm",
    "appointment.write",
    transitionRoute("confirm"),
  );
  r.post(
    "/api/v1/appointments/{appointment_id}/cancel",
    "appointment.write",
    transitionRoute("cancel"),
  );
  r.post(
    "/api/v1/appointments/{appointment_id}/check-in",
    "appointment.check_in",
    transitionRoute("check-in"),
  );
  r.post(
    "/api/v1/appointments/{appointment_id}/complete",
    "appointment.check_in",
    transitionRoute("complete"),
  );
  r.post(
    "/api/v1/appointments/{appointment_id}/miss",
    "appointment.check_in",
    transitionRoute("miss"),
  );
  r.post(
    "/api/v1/appointments/{appointment_id}/start",
    "appointment.check_in",
    transitionRoute("start"),
  );

  r.get("/api/v1/dashboard/kpis", null, kpisRoute);

  // CRM
  r.get("/api/v1/crm/tasks", "crm.task.read", (ctx): Reply => {
    const status = ctx.query.get("task_status");
    const rule = ctx.query.get("rule_key");
    const owner = ctx.query.get("owner_user_id");
    const patient = ctx.query.get("patient_id");
    const dueBy = ctx.query.get("due_by");
    const found = tasks
      .filter((t) => !status || t.status === status)
      .filter((t) => !rule || t.rule_key === rule)
      .filter((t) => !owner || t.owner_user_id === owner)
      .filter((t) => !patient || t.patient_id === patient)
      // the real API takes a DATE and reads it as that whole clinic day (+07:00)
      .filter((t) => !dueBy || Date.parse(t.due_at) <= Date.parse(`${dueBy}T23:59:59+07:00`))
      .toSorted((a, b) => a.due_at.localeCompare(b.due_at));
    return { body: paginate(found, ctx.query) };
  });
  r.get("/api/v1/crm/tasks/{task_id}", "crm.task.read", (ctx): Reply => ({
    body: findOr404(tasks, ctx.params.task_id ?? "", "việc chăm sóc"),
  }));
  r.post("/api/v1/crm/tasks/{task_id}/resolve", "crm.task.resolve", resolveTask);
  r.get("/api/v1/crm/activities", "crm.task.read", (ctx): Reply => {
    const patient = ctx.query.get("patient_id");
    const task = ctx.query.get("task_id");
    const found = activities
      .filter((a) => !patient || a.patient_id === patient)
      .filter((a) => !task || a.task_id === task);
    return { body: paginate(found, ctx.query) };
  });
  r.post("/api/v1/crm/activities", "crm.activity.write", (ctx): Reply => {
    const input = bodyOf<S["CrmActivityCreate"]>(ctx);
    const created: S["CrmActivityOut"] = {
      id: uid("act"),
      patient_id: input.patient_id,
      task_id: input.task_id ?? null,
      kind: "note",
      channel: input.channel,
      outcome: input.outcome ?? null,
      note: input.note,
      actor_user_id: session(ctx).userId,
      actor_name: null,
      occurred_at: isoFromNow(0),
      next_action_at: input.next_action_at ?? null,
      related_appointment_id: null,
    };
    activities.unshift(created);
    return { status: 201, body: created };
  });

  // inbox
  r.get("/api/v1/conversations", "conversation.read", (ctx): Reply => {
    const status = ctx.query.get("conversation_status");
    const assigned = ctx.query.get("assigned_user_id");
    const patient = ctx.query.get("patient_id");
    const pending = ctx.query.get("has_pending_review");
    const q = ctx.query.get("q");
    const found = conversations
      .filter((c) => !status || c.status === status)
      .filter((c) => !assigned || c.assigned_user_id === assigned)
      .filter((c) => !patient || c.patient_id === patient)
      .filter((c) => pending === null || String(c.has_pending_review) === pending)
      .filter(
        (c) =>
          !q ||
          foldForSearch(
            `${c.patient_display_name ?? ""} ${c.patient_code ?? ""} ${c.last_message_preview ?? ""}`,
          ).includes(foldForSearch(q)),
      )
      .toSorted((a, b) => (b.last_message_at ?? "").localeCompare(a.last_message_at ?? ""))
      .map((c) => ({ ...conversationSummary(c), viewers: viewersFor(c.id, session(ctx).userId) }));
    return { body: paginate(found, ctx.query) };
  });
  r.get("/api/v1/conversations/{conversation_id}", "conversation.read", (ctx): Reply => {
    const conv = findOr404(conversations, ctx.params.conversation_id ?? "", "hội thoại");
    return { body: { ...conv, viewers: viewersFor(conv.id, session(ctx).userId) } };
  });
  r.patch("/api/v1/conversations/{conversation_id}", "conversation.reply", (ctx): Reply => {
    const conv = findOr404(conversations, ctx.params.conversation_id ?? "", "hội thoại");
    const { version, assigned_user_id, status } = bodyOf<S["ConversationUpdate"]>(ctx);
    checkVersion(conv.version, version);
    if (assigned_user_id) assertAssignable(assigned_user_id);
    if (assigned_user_id !== undefined) conv.assigned_user_id = assigned_user_id;
    if (status) conv.status = status;
    conv.version += 1;
    return { body: conv };
  });
  r.get("/api/v1/conversations/{conversation_id}/messages", "conversation.read", (ctx): Reply => {
    const conv = findOr404(conversations, ctx.params.conversation_id ?? "", "hội thoại");
    const found = messages
      .filter((m) => m.conversation_id === conv.id)
      .toSorted((a, b) => a.created_at.localeCompare(b.created_at));
    return { body: paginate(found, ctx.query) };
  });
  r.post(
    "/api/v1/conversations/{conversation_id}/messages",
    "conversation.reply",
    sendStaffMessage,
  );
  r.post("/api/v1/conversations/{conversation_id}/read", "conversation.read", (ctx): Reply => {
    const conv = findOr404(conversations, ctx.params.conversation_id ?? "", "hội thoại");
    conv.unread_count = 0;
    return { status: 204 };
  });

  // review queue
  r.get("/api/v1/review-items", "review.read", (ctx): Reply => {
    const status = ctx.query.get("review_status");
    const kind = ctx.query.get("kind");
    const doctor = ctx.query.get("requires_doctor");
    const patient = ctx.query.get("patient_id");
    const conv = ctx.query.get("conversation_id");
    const found = reviewItems
      .filter((i) => !status || i.status === status)
      .filter((i) => !kind || i.kind === kind)
      .filter((i) => doctor === null || String(i.requires_doctor) === doctor)
      .filter((i) => !patient || i.patient_id === patient)
      .filter((i) => !conv || i.conversation_id === conv)
      .toSorted((a, b) => b.created_at.localeCompare(a.created_at));
    return { body: paginate(found, ctx.query) };
  });
  r.get("/api/v1/review-items/{item_id}", "review.read", (ctx): Reply => ({
    body: findOr404(reviewItems, ctx.params.item_id ?? "", "mục duyệt"),
  }));
  r.post("/api/v1/review-items/{item_id}/approve", "review.decide", (ctx): Reply => {
    const item = findOr404(reviewItems, ctx.params.item_id ?? "", "mục duyệt");
    const input = bodyOf<S["ReviewApprove"]>(ctx);
    return once(ctx, `approve:${item.id}`, (): Reply => {
      checkVersion(item.version, input.version);
      decideGuard(ctx, item);
      const finalText = (input.final_text ?? item.draft_text ?? "").trim();
      const needsText = item.kind === "reply_draft" || item.kind === "followup_draft";
      if (needsText && !finalText)
        fail(422, "validation_failed", "Nội dung gửi không được để trống.");
      item.status = "approved";
      item.final_text = finalText || null;
      item.decision_note = input.note ?? null;
      item.decided_at = isoFromNow(0);
      item.decided_by = session(ctx).userId;
      item.version += 1;
      const conv = conversations.find((c) => c.id === item.conversation_id);
      if (conv && needsText && (input.send ?? true)) {
        messages.push({
          id: uid("msg"),
          conversation_id: conv.id,
          direction: "outbound",
          sender_type: "ai_draft",
          sender_user_id: session(ctx).userId,
          body: finalText,
          status: "sent",
          created_at: isoFromNow(0),
          sent_at: isoFromNow(0),
          proactive: false,
          review_item_id: item.id,
          error_code: null,
        });
        conv.last_message_at = isoFromNow(0);
        conv.last_message_preview = finalText;
      }
      closeLinkedConversation(item);
      return { body: item };
    });
  });
  r.post("/api/v1/review-items/{item_id}/reject", "review.decide", (ctx): Reply => {
    const item = findOr404(reviewItems, ctx.params.item_id ?? "", "mục duyệt");
    const input = bodyOf<S["ReviewReject"]>(ctx);
    checkVersion(item.version, input.version);
    decideGuard(ctx, item);
    if (!input.reason.trim()) fail(422, "validation_failed", "Nhập lý do từ chối.");
    item.status = "rejected";
    item.decision_note = input.reason;
    item.decided_at = isoFromNow(0);
    item.decided_by = session(ctx).userId;
    item.version += 1;
    closeLinkedConversation(item);
    return { body: item };
  });
  r.post("/api/v1/review-items/{item_id}/escalate", "review.decide", (ctx): Reply => {
    const item = findOr404(reviewItems, ctx.params.item_id ?? "", "mục duyệt");
    const input = bodyOf<S["ReviewEscalate"]>(ctx);
    checkVersion(item.version, input.version);
    if (item.status !== "pending") fail(409, "invalid_state", "Mục này đã được xử lý.");
    item.status = "escalated";
    item.requires_doctor = true;
    item.decision_note = input.note ?? null;
    item.version += 1;
    return { body: item };
  });
}
