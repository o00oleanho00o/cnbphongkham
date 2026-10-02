// Mock of the clinic operations API: patients (+360), consents, appointments, CRM tasks and activities,
// conversations (Inbox) and the review queue. State lives in module variables (see mock/data/clinic.ts).
import { foldForSearch } from "../../src/lib/admin/shared/fold-for-search";
import {
  activities,
  appointments,
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
    plans: isTreating
      ? [
          {
            id: uuid(1, 13),
            episode_id: uuid(1, 12),
            service_code: "laser-co2",
            title: "Laser CO2 phục hồi da (4 buổi)",
            status: "active",
            total_sessions: 4,
            completed_sessions: 2,
          },
        ]
      : [],
    recent_sessions: isTreating
      ? [
          {
            id: uuid(1, 14),
            plan_id: uuid(1, 13),
            doctor_id: p.doctor_id ?? null,
            performed_at: isoFromNow(-2 * 86_400_000),
            title: "Buổi 2/4 Laser CO2",
            status: "completed",
            protocol_id: "laser-co2",
          },
        ]
      : [],
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
    ].toSorted((a, b) => b.at.localeCompare(a.at)),
  };
}

// -------------------------------------------------------------- appointments

const TRANSITIONS: Record<string, { from: S["AppointmentStatus"][]; to: S["AppointmentStatus"] }> =
  {
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

function createAppointment(input: S["AppointmentCreate"], by: string): S["AppointmentOut"] {
  const p = patientById(input.patient_id);
  if (!p) fail(404, "not_found", "Không tìm thấy bệnh nhân.");
  const clash = appointments.some(
    (a) =>
      a.doctor_id === (input.doctor_id ?? p.doctor_id ?? null) &&
      a.starts_at === input.starts_at &&
      a.status !== "cancelled",
  );
  if (clash) fail(409, "appointment_conflict", "Bác sĩ đã có lịch vào giờ này. Chọn giờ khác.");
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
    const cleaned = Object.fromEntries(
      Object.entries(patch).filter(([, v]) => v !== undefined && v !== null),
    );
    Object.assign(appt, cleaned, { version: appt.version + 1 });
    return { body: appt };
  });
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
    "session.write",
    transitionRoute("complete"),
  );
  r.post(
    "/api/v1/appointments/{appointment_id}/miss",
    "appointment.write",
    transitionRoute("miss"),
  );
  r.post("/api/v1/appointments/{appointment_id}/start", "session.write", transitionRoute("start"));

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
