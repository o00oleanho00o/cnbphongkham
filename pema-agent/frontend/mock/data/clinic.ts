// Fictional clinic data for the operations screens (patients, tasks, inbox, review queue, templates).
// Names come from the synthetic set already in the repo (prototype/shared); there is no real record, phone
// number, photo or token here. Times are relative to "now" so "Việc hôm nay" always has work to show.
import { USERS } from "../auth";
import { DAY, HOUR, MIN, isoFromNow, uuid, type Schemas } from "../core";

type S = Schemas;

export const DOCTOR_TAM = uuid(3, 1);
export const DOCTOR_AN = uuid(11, 1);
export const DOCTOR_MAI = uuid(12, 1);
export const CS_MAI_ANH = uuid(4, 1);

export const DOCTOR_NAMES: Record<string, string> = {
  [DOCTOR_TAM]: "BS. Lê Minh Tâm",
  [DOCTOR_AN]: "BS. Trương Hoài An",
  [DOCTOR_MAI]: "BS. Đoàn Thị Mai",
};

const OWNER_NAMES: Record<string, string> = Object.fromEntries(
  USERS.map((u) => [u.id, u.display_name]),
);

type PatientSeed = {
  n: number;
  full_name: string;
  gender: S["Gender"];
  birth_date: string;
  doctor_id: string;
  source: string;
  opt_out?: boolean;
};

const PATIENT_SEEDS: PatientSeed[] = [
  {
    n: 1,
    full_name: "Nguyễn Thu Hà",
    gender: "female",
    birth_date: "1991-03-14",
    doctor_id: DOCTOR_TAM,
    source: "Giới thiệu",
  },
  {
    n: 2,
    full_name: "Trần Minh Anh",
    gender: "female",
    birth_date: "1988-07-02",
    doctor_id: DOCTOR_AN,
    source: "Zalo",
  },
  {
    n: 3,
    full_name: "Lê Hoàng Yến",
    gender: "female",
    birth_date: "1995-11-23",
    doctor_id: DOCTOR_TAM,
    source: "Facebook",
  },
  {
    n: 4,
    full_name: "Phạm Quốc Bảo",
    gender: "male",
    birth_date: "1984-01-30",
    doctor_id: DOCTOR_AN,
    source: "Khách cũ",
  },
  {
    n: 5,
    full_name: "Võ Ngọc Trâm",
    gender: "female",
    birth_date: "1990-05-18",
    doctor_id: DOCTOR_TAM,
    source: "Giới thiệu",
  },
  {
    n: 6,
    full_name: "Đặng Gia Linh",
    gender: "female",
    birth_date: "1999-09-25",
    doctor_id: DOCTOR_MAI,
    source: "Zalo",
  },
  {
    n: 7,
    full_name: "Bùi Khánh Vy",
    gender: "female",
    birth_date: "1993-02-09",
    doctor_id: DOCTOR_MAI,
    source: "Facebook",
  },
  {
    n: 8,
    full_name: "Hồ Thanh Tùng",
    gender: "male",
    birth_date: "1979-12-12",
    doctor_id: DOCTOR_TAM,
    source: "Khách cũ",
  },
  {
    n: 9,
    full_name: "Ngô Mỹ Duyên",
    gender: "female",
    birth_date: "1986-06-06",
    doctor_id: DOCTOR_AN,
    source: "Khách cũ",
    opt_out: true,
  },
  {
    n: 10,
    full_name: "Đỗ Phương Thảo",
    gender: "female",
    birth_date: "1992-09-24",
    doctor_id: DOCTOR_MAI,
    source: "Zalo",
  },
];

export const patients: S["PatientOut"][] = PATIENT_SEEDS.map((p) => ({
  id: uuid(p.n, 2),
  code: `P${String(p.n).padStart(3, "0")}`,
  full_name: p.full_name,
  gender: p.gender,
  birth_date: p.birth_date,
  doctor_id: p.doctor_id,
  doctor_name: DOCTOR_NAMES[p.doctor_id] ?? null,
  cs_owner_id: CS_MAI_ANH,
  cs_owner_name: OWNER_NAMES[CS_MAI_ANH] ?? null,
  phone: null,
  source: p.source,
  first_contact_at: isoFromNow(-(200 + p.n * 11) * DAY).slice(0, 10),
  marketing_opt_out: p.opt_out ?? false,
  version: 1,
}));

export function patientById(id: string): S["PatientOut"] | undefined {
  return patients.find((p) => p.id === id);
}

export function patientRef(n: number): S["PatientOut"] {
  const p = patients[n - 1];
  if (!p) throw new Error(`no patient ${n}`);
  return p;
}

// ---------------------------------------------------------------- CRM tasks

type TaskSeed = {
  n: number;
  patient: number;
  rule: S["RuleKey"];
  dueMs: number;
  priority: S["TaskPriority"];
  reason: string;
  action: string;
  status?: S["TaskStatus"];
  owner?: string;
};

const TASK_SEEDS: TaskSeed[] = [
  {
    n: 1,
    patient: 1,
    rule: "d1",
    dueMs: -1 * HOUR,
    priority: "high",
    reason: "Sau thủ thuật Laser CO2 hôm qua",
    action:
      "Nhắn Zalo hỏi thăm sau thủ thuật: “Chào chị Hà, em là Mai Anh bên phòng khám Pema. Hôm qua chị làm laser, hôm nay da chị có đỏ rát hay khó chịu gì không ạ? Chị nhớ thoa kem dưỡng và chống nắng theo hướng dẫn nhé. Cần gì chị nhắn em ngay ạ.”",
  },
  {
    n: 2,
    patient: 2,
    rule: "d3",
    dueMs: 1 * HOUR,
    priority: "normal",
    reason: "Mốc D+3 sau thủ thuật",
    action:
      "Nhắn Zalo nhắc khách tự chụp ảnh tiến triển: “Chào chị Minh Anh, đã 3 ngày kể từ buổi làm da. Chị chụp giúp em 1 ảnh vùng da ở nơi đủ sáng và gửi lại để bác sĩ theo dõi nhé ạ.”",
  },
  {
    n: 3,
    patient: 3,
    rule: "d7",
    dueMs: 2 * HOUR,
    priority: "high",
    reason: "Bác sĩ review D+7",
    action: "Chuyển bác sĩ xem ảnh tiến triển D+7 và ghi lại đề xuất bước tiếp theo.",
    owner: DOCTOR_TAM,
  },
  {
    n: 4,
    patient: 4,
    rule: "due",
    dueMs: 3 * HOUR,
    priority: "normal",
    reason: "Đến hạn tái khám hôm nay",
    action: "Gọi nhắc lịch tái khám đã đến hạn và đề xuất khung giờ phù hợp.",
  },
  {
    n: 5,
    patient: 5,
    rule: "overdue",
    dueMs: -2 * DAY,
    priority: "high",
    reason: "Quá hạn tái khám 2 ngày",
    action: "Gọi hỏi lý do chưa tái khám, đề xuất đặt lại lịch trong tuần.",
  },
  {
    n: 6,
    patient: 6,
    rule: "no_show",
    dueMs: -1 * DAY,
    priority: "high",
    reason: "Vắng hẹn hôm qua",
    action: "Gọi hỏi thăm và hỗ trợ đặt lại lịch sau lần vắng hẹn.",
  },
  {
    n: 7,
    patient: 7,
    rule: "abandoned",
    dueMs: 4 * HOUR,
    priority: "normal",
    reason: "Còn 2 buổi chưa thực hiện",
    action:
      "Nhắn Zalo hỏi thăm và nhắc tiếp tục liệu trình còn lại: “Chào chị Vy, liệu trình của chị còn 2 buổi. Chị muốn em sắp xếp lịch vào tuần này không ạ?”",
  },
  {
    n: 8,
    patient: 8,
    rule: "dormant90",
    dueMs: 5 * HOUR,
    priority: "low",
    reason: "Chưa quay lại 90 ngày",
    action: "Gọi kết nối lại, hỏi nhu cầu chăm sóc da hiện tại.",
  },
  {
    n: 9,
    patient: 10,
    rule: "birthday",
    dueMs: 6 * HOUR,
    priority: "low",
    reason: "Sinh nhật trong tuần",
    action:
      "Nhắn Zalo chúc mừng sinh nhật (gửi tay, hệ thống không tự gửi): “Chúc mừng sinh nhật chị Phương Thảo! Phòng khám Pema chúc chị luôn khỏe và rạng rỡ ạ.”",
  },
  {
    n: 10,
    patient: 9,
    rule: "dormant180",
    dueMs: -3 * DAY,
    priority: "low",
    reason: "Chưa quay lại 180 ngày",
    action:
      "Gọi kết nối lại. Khách đã từ chối tin quảng bá: chỉ chăm sóc, không giới thiệu ưu đãi.",
    status: "resolved",
  },
];

export const tasks: S["CrmTaskOut"][] = TASK_SEEDS.map((t) => ({
  id: uuid(t.n, 3),
  task_key: `CRM:${t.rule}:P${String(t.patient).padStart(3, "0")}:${t.n}`,
  patient_id: patientRef(t.patient).id,
  patient_code: patientRef(t.patient).code,
  rule_key: t.rule,
  status: t.status ?? "open",
  priority: t.priority,
  reason: t.reason,
  suggested_action: t.action,
  due_at: isoFromNow(t.dueMs),
  created_at: isoFromNow(-1 * DAY),
  owner_user_id: t.owner ?? CS_MAI_ANH,
  owner_name: OWNER_NAMES[t.owner ?? CS_MAI_ANH] ?? DOCTOR_NAMES[t.owner ?? ""] ?? null,
  resolution: t.status === "resolved" ? "no_need" : null,
  resolved_at: t.status === "resolved" ? isoFromNow(-1 * DAY) : null,
  source_event_id: `evt-${t.n}`,
  related_appointment_id: null,
  version: 1,
}));

export const activities: S["CrmActivityOut"][] = [
  {
    id: uuid(1, 4),
    patient_id: patientRef(1).id,
    task_id: null,
    kind: "contact",
    channel: "call",
    outcome: "no_need",
    note: "Đã gọi tư vấn sau buổi laser đầu, khách hài lòng, hẹn buổi 2 sau 4 tuần.",
    actor_user_id: CS_MAI_ANH,
    actor_name: OWNER_NAMES[CS_MAI_ANH] ?? null,
    occurred_at: isoFromNow(-8 * DAY),
    next_action_at: null,
    related_appointment_id: null,
  },
  {
    id: uuid(2, 4),
    patient_id: patientRef(5).id,
    task_id: null,
    kind: "contact",
    channel: "zalo",
    outcome: "unanswered",
    note: "Đã nhắn Zalo hỏi lịch tái khám, khách chưa trả lời.",
    actor_user_id: CS_MAI_ANH,
    actor_name: OWNER_NAMES[CS_MAI_ANH] ?? null,
    occurred_at: isoFromNow(-3 * DAY),
    next_action_at: isoFromNow(-2 * DAY),
    related_appointment_id: null,
  },
];

// ------------------------------------------------------------- Appointments

const appointment = (
  n: number,
  patient: number,
  startsMs: number,
  status: S["AppointmentStatus"],
  note: string,
): S["AppointmentOut"] => ({
  id: uuid(n, 5),
  patient_id: patientRef(patient).id,
  patient_code: patientRef(patient).code,
  doctor_id: patientRef(patient).doctor_id ?? null,
  starts_at: isoFromNow(startsMs),
  duration_min: 45,
  status,
  note,
  created_by: CS_MAI_ANH,
  cancel_reason: null,
  cancelled_at: null,
  missed_at: status === "missed" ? isoFromNow(startsMs + HOUR) : null,
  version: 1,
});

/** `YYYY-MM-DD` of the clinic's today (+07:00), whatever the zone of the machine. */
export function clinicToday(offsetDays = 0): string {
  return isoFromNow(offsetDays * DAY).slice(0, 10);
}

/** An appointment on a clinic day at a clock time ("08:30"); the doctor is the one given, not the patient's. */
const onDay = (
  n: number,
  patient: number,
  dayOffset: number,
  clock: string,
  doctor: string,
  status: S["AppointmentStatus"],
  note: string,
  duration = 30,
): S["AppointmentOut"] => {
  const at = `${clinicToday(dayOffset)}T${clock}:00+07:00`;
  return {
    ...appointment(n, patient, 0, status, note),
    doctor_id: doctor,
    starts_at: at,
    duration_min: duration,
    missed_at: status === "missed" ? at : null,
    cancel_reason: status === "cancelled" ? "Bệnh nhân bận việc đột xuất" : null,
    cancelled_at: status === "cancelled" ? at : null,
  };
};

export const appointments: S["AppointmentOut"][] = [
  appointment(1, 1, 26 * DAY, "booked", "Buổi 3/4 Laser CO2"),
  appointment(2, 1, -2 * DAY, "completed", "Buổi 2/4 Laser CO2"),
  appointment(3, 4, 5 * HOUR, "confirmed", "Tái khám"),
  appointment(4, 6, -1 * DAY, "missed", "Tái khám"),
  appointment(5, 2, -3 * DAY, "completed", "Peel da nhẹ"),
  // A full clinic day for the schedule board (every reception status once) and a few on the next days.
  onDay(6, 2, 0, "08:00", DOCTOR_AN, "completed", "Tái khám sau peel"),
  onDay(7, 3, 0, "08:30", DOCTOR_TAM, "in_progress", "Laser CO2 buổi 2/4", 45),
  onDay(8, 5, 0, "09:00", DOCTOR_AN, "arrived", "Tư vấn da liễu"),
  onDay(9, 7, 0, "09:30", DOCTOR_MAI, "confirmed", "Chăm sóc theo chỉ định", 45),
  onDay(10, 8, 0, "10:00", DOCTOR_TAM, "booked", "Tái khám"),
  onDay(11, 9, 0, "10:30", DOCTOR_AN, "missed", "Tái khám"),
  onDay(12, 10, 0, "14:00", DOCTOR_MAI, "booked", "Tư vấn chuyên sâu", 45),
  onDay(13, 6, 0, "15:00", DOCTOR_TAM, "cancelled", "Laser theo chỉ định", 45),
  onDay(14, 1, 1, "09:00", DOCTOR_TAM, "confirmed", "Buổi 3/4 Laser CO2", 45),
  onDay(15, 4, 2, "10:30", DOCTOR_MAI, "booked", "Tái khám"),
  onDay(16, 2, 4, "14:30", DOCTOR_AN, "booked", "Peel da nhẹ"),
];

// ----------------------------------------------------------------- Consents

export const consents: Record<string, S["ConsentOut"][]> = Object.fromEntries(
  patients.map((p, i) => [
    p.id,
    [
      {
        id: uuid(100 + i, 6),
        kind: "messaging",
        granted: true,
        granted_at: isoFromNow(-150 * DAY),
        revoked_at: null,
        source: "Phiếu giấy",
      },
      {
        id: uuid(200 + i, 6),
        kind: "marketing",
        granted: !p.marketing_opt_out && i % 3 !== 0,
        granted_at: isoFromNow(-150 * DAY),
        revoked_at: null,
        source: "Phiếu giấy",
      },
      {
        id: uuid(300 + i, 6),
        kind: "media",
        granted: i % 2 === 0,
        granted_at: i % 2 === 0 ? isoFromNow(-140 * DAY) : null,
        revoked_at: null,
        source: i % 2 === 0 ? "Phiếu giấy" : null,
      },
    ] satisfies S["ConsentOut"][],
  ]),
);

// ------------------------------------------------------------ Conversations

type ConvSeed = {
  n: number;
  patient: number | null;
  status: S["ConversationStatus"];
  unread: number;
  pending: boolean;
  last: string;
  lastAgoMs: number;
  externalRef: string;
};

const CONV_SEEDS: ConvSeed[] = [
  {
    n: 1,
    patient: 1,
    status: "pending_review",
    unread: 2,
    pending: true,
    last: "Dạ em thấy da đỏ hơn hôm qua một chút, có sao không ạ?",
    lastAgoMs: 12 * MIN,
    externalRef: "zalo:u-demo-001",
  },
  {
    n: 2,
    patient: 2,
    status: "handoff",
    unread: 1,
    pending: true,
    last: "Em bị chảy máu chỗ vừa làm và hơi sốt, em phải làm sao?",
    lastAgoMs: 25 * MIN,
    externalRef: "zalo:u-demo-002",
  },
  {
    n: 3,
    patient: 3,
    status: "handoff",
    unread: 1,
    pending: true,
    last: "[Khách gửi ảnh]",
    lastAgoMs: 50 * MIN,
    externalRef: "zalo:u-demo-003",
  },
  {
    n: 4,
    patient: null,
    status: "pending_review",
    unread: 1,
    pending: true,
    last: "Chào phòng khám, mình muốn hỏi giá peel da",
    lastAgoMs: 2 * HOUR,
    externalRef: "zalo:u-demo-004",
  },
  {
    n: 5,
    patient: 4,
    status: "open",
    unread: 0,
    pending: false,
    last: "Cảm ơn em, chiều nay anh qua nhé",
    lastAgoMs: 3 * HOUR,
    externalRef: "zalo:u-demo-005",
  },
  {
    n: 6,
    patient: 8,
    status: "closed",
    unread: 0,
    pending: false,
    last: "Dạ cảm ơn phòng khám",
    lastAgoMs: 5 * DAY,
    externalRef: "zalo:u-demo-006",
  },
];

export const conversations: S["ConversationOut"][] = CONV_SEEDS.map((c) => {
  const patient = c.patient === null ? null : patientRef(c.patient);
  return {
    id: uuid(c.n, 7),
    channel: "zalo_bot",
    external_ref: c.externalRef,
    status: c.status,
    patient_id: patient?.id ?? null,
    patient_code: patient?.code ?? null,
    patient_display_name: patient?.full_name ?? null,
    assigned_user_id: c.status === "open" ? CS_MAI_ANH : null,
    unread_count: c.unread,
    has_pending_review: c.pending,
    last_message_at: isoFromNow(-c.lastAgoMs),
    last_message_preview: c.last,
    created_at: isoFromNow(-10 * DAY),
    version: 1,
  };
});

const message = (
  conv: number,
  n: number,
  agoMs: number,
  direction: S["MessageDirection"],
  sender: S["SenderType"],
  body: string | null,
  extra: Partial<S["MessageOut"]> = {},
): S["MessageOut"] => ({
  id: uuid(conv * 100 + n, 8),
  conversation_id: uuid(conv, 7),
  direction,
  sender_type: sender,
  body,
  status: direction === "inbound" ? "received" : "sent",
  created_at: isoFromNow(-agoMs),
  sent_at: direction === "outbound" ? isoFromNow(-agoMs) : null,
  proactive: false,
  sender_user_id: sender === "staff" ? CS_MAI_ANH : null,
  review_item_id: null,
  error_code: null,
  ...extra,
});

export const messages: S["MessageOut"][] = [
  message(1, 1, 3 * DAY, "inbound", "patient", "Chào phòng khám, em là Hà, hôm qua em làm laser."),
  message(
    1,
    2,
    3 * DAY - MIN,
    "outbound",
    "staff",
    "Chào chị Hà, em là Mai Anh. Chị cần hỗ trợ gì ạ?",
    { sender_type: "staff" },
  ),
  message(1, 3, 30 * MIN, "inbound", "patient", "Em thoa kem như hướng dẫn rồi."),
  message(
    1,
    4,
    13 * MIN,
    "inbound",
    "patient",
    "Dạ em thấy da đỏ hơn hôm qua một chút, có sao không ạ?",
  ),
  message(
    1,
    5,
    12 * MIN,
    "outbound",
    "ai_draft",
    "Chào chị Hà, da hơi đỏ nhẹ trong 2 đến 3 ngày đầu sau laser là thường gặp. Chị tiếp tục thoa kem dưỡng ẩm, tránh nắng và không tự bóc vảy. Nếu đỏ rát tăng hoặc có chảy dịch, chị nhắn em để bác sĩ xem ngay nhé.",
    { status: "draft", review_item_id: uuid(1, 9) },
  ),
  message(2, 1, 40 * MIN, "inbound", "patient", "Chào em, hôm qua chị làm peel ở phòng khám."),
  message(
    2,
    2,
    25 * MIN,
    "inbound",
    "patient",
    "Em bị chảy máu chỗ vừa làm và hơi sốt, em phải làm sao?",
  ),
  message(
    2,
    3,
    24 * MIN,
    "outbound",
    "system",
    "Tin của chị đã được chuyển cho bác sĩ. Nhân viên sẽ liên hệ chị ngay.",
    { status: "sent" },
  ),
  message(3, 1, 55 * MIN, "inbound", "patient", "Em gửi ảnh vùng da sau 1 tuần ạ."),
  message(3, 2, 50 * MIN, "inbound", "patient", null),
  message(
    3,
    3,
    49 * MIN,
    "outbound",
    "system",
    "Em đã nhận ảnh của chị và chuyển cho nhân viên xem. Em sẽ phản hồi chị sớm ạ.",
    { status: "sent" },
  ),
  message(4, 1, 2 * HOUR, "inbound", "patient", "Chào phòng khám, mình muốn hỏi giá peel da"),
  message(5, 1, 4 * HOUR, "inbound", "patient", "Chiều nay mình qua tái khám được không em?"),
  message(
    5,
    2,
    3 * HOUR + 30 * MIN,
    "outbound",
    "staff",
    "Dạ được ạ, anh qua lúc 15h giúp em nhé.",
  ),
  message(5, 3, 3 * HOUR, "inbound", "patient", "Cảm ơn em, chiều nay anh qua nhé"),
  message(
    6,
    1,
    5 * DAY,
    "outbound",
    "staff",
    "Chào anh Tùng, phòng khám nhắc anh lịch kiểm tra da định kỳ ạ.",
  ),
  message(6, 2, 5 * DAY - MIN, "inbound", "patient", "Dạ cảm ơn phòng khám"),
];

// ------------------------------------------------------------- Review queue

const source = (
  id: string,
  title: string,
  snippet: string,
  score: number,
): S["SourceCitation"] => ({
  source_id: id,
  title,
  snippet,
  score,
});

export const reviewItems: S["ReviewItemOut"][] = [
  {
    id: uuid(1, 9),
    kind: "reply_draft",
    status: "pending",
    origin: "agent_turn",
    conversation_id: uuid(1, 7),
    patient_id: patientRef(1).id,
    patient_code: patientRef(1).code,
    draft_text:
      "Chào chị Hà, da hơi đỏ nhẹ trong 2 đến 3 ngày đầu sau laser là thường gặp. Chị tiếp tục thoa kem dưỡng ẩm, tránh nắng và không tự bóc vảy. Nếu đỏ rát tăng hoặc có chảy dịch, chị nhắn em để bác sĩ xem ngay nhé.",
    final_text: null,
    risk_level: "attention",
    requires_doctor: false,
    red_flags: [],
    sources: [
      source(
        "kb-sau-laser",
        "Hướng dẫn chăm sóc da sau laser (mẫu)",
        "Da có thể đỏ nhẹ, hơi rát 2 đến 3 ngày đầu. Dùng kem dưỡng ẩm dịu nhẹ, chống nắng, không bóc vảy.",
        0.82,
      ),
      source(
        "kb-dau-hieu",
        "Dấu hiệu cần liên hệ phòng khám (mẫu)",
        "Liên hệ ngay khi đỏ rát tăng, chảy dịch, chảy máu, sốt hoặc sưng nhiều.",
        0.74,
      ),
    ],
    model: "qwen3-8b",
    prompt_version: "cskh-da-lieu@3",
    job_id: null,
    payload: null,
    version: 1,
    created_at: isoFromNow(-12 * MIN),
    decided_at: null,
    decided_by: null,
    decision_note: null,
  },
  {
    id: uuid(2, 9),
    kind: "triage_alert",
    status: "pending",
    origin: "policy",
    conversation_id: uuid(2, 7),
    patient_id: patientRef(2).id,
    patient_code: patientRef(2).code,
    draft_text: null,
    final_text: null,
    risk_level: "red_flag",
    requires_doctor: true,
    red_flags: ["chảy máu", "sốt"],
    sources: [],
    model: null,
    prompt_version: null,
    job_id: null,
    payload: { matched: ["chảy máu", "sốt"], model_called: false },
    version: 1,
    created_at: isoFromNow(-25 * MIN),
    decided_at: null,
    decided_by: null,
    decision_note: null,
  },
  {
    id: uuid(3, 9),
    kind: "media_flag",
    status: "pending",
    origin: "policy",
    conversation_id: uuid(3, 7),
    patient_id: patientRef(3).id,
    patient_code: patientRef(3).code,
    draft_text: null,
    final_text: null,
    risk_level: "attention",
    requires_doctor: false,
    red_flags: [],
    sources: [],
    model: null,
    prompt_version: null,
    job_id: null,
    payload: { media_count: 1, action: "flag_and_hand_off" },
    version: 1,
    created_at: isoFromNow(-50 * MIN),
    decided_at: null,
    decided_by: null,
    decision_note: null,
  },
  {
    id: uuid(4, 9),
    kind: "followup_draft",
    status: "pending",
    origin: "crm_rule",
    conversation_id: null,
    patient_id: patientRef(5).id,
    patient_code: patientRef(5).code,
    draft_text:
      "Chào chị Trâm, đã đến thời gian tái khám sau liệu trình của chị. Chị rảnh khung giờ nào trong tuần này để em sắp xếp lịch với bác sĩ ạ?",
    final_text: null,
    risk_level: "normal",
    requires_doctor: false,
    red_flags: [],
    sources: [
      source(
        "tpl-tai-kham",
        "Mẫu nhắc tái khám (đã duyệt)",
        "Nhắc khách đến hạn tái khám và hỏi khung giờ thuận tiện.",
        0.91,
      ),
    ],
    model: "qwen3-8b",
    prompt_version: "followup@2",
    job_id: "job-demo-4",
    payload: null,
    version: 1,
    created_at: isoFromNow(-2 * HOUR),
    decided_at: null,
    decided_by: null,
    decision_note: null,
  },
  {
    id: uuid(5, 9),
    kind: "identity_check",
    status: "pending",
    origin: "policy",
    conversation_id: uuid(4, 7),
    patient_id: null,
    patient_code: null,
    draft_text: null,
    final_text: null,
    risk_level: "attention",
    requires_doctor: false,
    red_flags: [],
    sources: [],
    model: null,
    prompt_version: null,
    job_id: null,
    payload: { external_user_ref: "zalo:u-demo-004", candidates: 0 },
    version: 1,
    created_at: isoFromNow(-2 * HOUR),
    decided_at: null,
    decided_by: null,
    decision_note: null,
  },
  {
    id: uuid(6, 9),
    kind: "reply_draft",
    status: "approved",
    origin: "agent_turn",
    conversation_id: uuid(5, 7),
    patient_id: patientRef(4).id,
    patient_code: patientRef(4).code,
    draft_text: "Dạ được ạ, anh qua lúc 15h giúp em nhé.",
    final_text: "Dạ được ạ, anh qua lúc 15h giúp em nhé.",
    risk_level: "normal",
    requires_doctor: false,
    red_flags: [],
    sources: [],
    model: "qwen3-8b",
    prompt_version: "cskh-da-lieu@3",
    job_id: null,
    payload: null,
    version: 2,
    created_at: isoFromNow(-4 * HOUR),
    decided_at: isoFromNow(-3 * HOUR - 30 * MIN),
    decided_by: CS_MAI_ANH,
    decision_note: null,
  },
  {
    id: uuid(7, 9),
    kind: "reply_draft",
    status: "rejected",
    origin: "agent_turn",
    conversation_id: uuid(6, 7),
    patient_id: patientRef(8).id,
    patient_code: patientRef(8).code,
    draft_text: "Anh nên dùng kem trị mụn nồng độ cao để hết nhanh hơn ạ.",
    final_text: null,
    risk_level: "attention",
    requires_doctor: false,
    red_flags: [],
    sources: [],
    model: "qwen3-8b",
    prompt_version: "cskh-da-lieu@3",
    job_id: null,
    payload: null,
    version: 2,
    created_at: isoFromNow(-6 * DAY),
    decided_at: isoFromNow(-6 * DAY + HOUR),
    decided_by: CS_MAI_ANH,
    decision_note: "Nháp tư vấn thuốc không có nguồn, không gửi.",
  },
];

// ---------------------------------------------------------------- Templates

export const templates: S["MessageTemplateOut"][] = [
  {
    id: uuid(1, 10),
    template_key: "nhac-tai-kham",
    title: "Nhắc lịch tái khám",
    body: "Chào {ten_khach}, phòng khám Pema nhắc chị đã đến hạn tái khám. Chị rảnh khung giờ nào trong tuần này để em sắp xếp lịch với bác sĩ ạ?",
    marketing: false,
    active: true,
    approved_at: isoFromNow(-30 * DAY),
    approved_by: DOCTOR_TAM,
    version: 2,
  },
  {
    id: uuid(2, 10),
    template_key: "hoi-tham-sau-thu-thuat",
    title: "Hỏi thăm sau thủ thuật (D+1)",
    body: "Chào {ten_khach}, hôm qua chị vừa làm thủ thuật tại Pema. Hôm nay da chị thế nào ạ? Nếu thấy đỏ rát tăng hoặc có chảy dịch, chị nhắn ngay để bác sĩ xem nhé.",
    marketing: false,
    active: true,
    approved_at: isoFromNow(-30 * DAY),
    approved_by: DOCTOR_TAM,
    version: 3,
  },
  {
    id: uuid(3, 10),
    template_key: "nhac-gui-anh-tien-trien",
    title: "Nhắc gửi ảnh tiến triển (D+3)",
    body: "Chào {ten_khach}, đã 3 ngày kể từ buổi làm da. Chị chụp 1 ảnh vùng da nơi đủ sáng và gửi lại để bác sĩ theo dõi nhé ạ.",
    marketing: false,
    active: true,
    approved_at: isoFromNow(-12 * DAY),
    approved_by: DOCTOR_MAI,
    version: 1,
  },
  {
    id: uuid(4, 10),
    template_key: "uu-dai-thang-10",
    title: "Ưu đãi chăm sóc da tháng 10",
    body: "Chào {ten_khach}, tháng này Pema có chương trình soi da miễn phí cho khách cũ. Chị muốn em giữ lịch không ạ?",
    marketing: true,
    active: false,
    approved_at: null,
    approved_by: null,
    version: 1,
  },
  {
    id: uuid(5, 10),
    template_key: "nhac-lich-hen",
    title: "Nhắc lịch hẹn ngày mai",
    body: "Chào {ten_khach}, phòng khám Pema nhắc chị có lịch hẹn vào {gio_hen} ngày mai. Chị nhắn em nếu cần đổi lịch nhé.",
    marketing: false,
    active: false,
    approved_at: null,
    approved_by: null,
    version: 2,
  },
];

// ---------------------------------------------------------------- CRM rules

type RuleSeed = {
  key: S["RuleKey"];
  delay: number;
  priority: S["TaskPriority"];
  mode: S["RuleSendMode"];
  action: string;
  trigger: string;
};

const RULE_SEEDS: RuleSeed[] = [
  {
    key: "d1",
    delay: 1,
    priority: "high",
    mode: "draft_for_review",
    action: "Nhắn Zalo hỏi thăm sau thủ thuật",
    trigger: "Một ngày sau thủ thuật có protocol",
  },
  {
    key: "d3",
    delay: 3,
    priority: "normal",
    mode: "draft_for_review",
    action: "Nhắn Zalo nhắc khách gửi ảnh tiến triển",
    trigger: "Ba ngày sau thủ thuật",
  },
  {
    key: "d7",
    delay: 7,
    priority: "high",
    mode: "staff_task",
    action: "Chuyển bác sĩ xem ảnh tiến triển D+7",
    trigger: "Bảy ngày sau thủ thuật",
  },
  {
    key: "due",
    delay: 0,
    priority: "normal",
    mode: "staff_task",
    action: "Gọi nhắc lịch tái khám đã đến hạn",
    trigger: "Ngày dự kiến tái khám",
  },
  {
    key: "overdue",
    delay: 7,
    priority: "high",
    mode: "staff_task",
    action: "Gọi hỏi lý do chưa tái khám",
    trigger: "Quá hạn tái khám 7 ngày",
  },
  {
    key: "no_show",
    delay: 1,
    priority: "high",
    mode: "staff_task",
    action: "Gọi hỏi thăm và hỗ trợ đặt lại lịch",
    trigger: "Vắng hẹn",
  },
  {
    key: "abandoned",
    delay: 14,
    priority: "normal",
    mode: "draft_for_review",
    action: "Nhắn Zalo nhắc tiếp tục liệu trình",
    trigger: "Còn buổi chưa làm sau 14 ngày",
  },
  {
    key: "dormant90",
    delay: 90,
    priority: "low",
    mode: "staff_task",
    action: "Gọi kết nối lại",
    trigger: "Chưa quay lại 90 ngày",
  },
  {
    key: "dormant180",
    delay: 180,
    priority: "low",
    mode: "staff_task",
    action: "Gọi kết nối lại",
    trigger: "Chưa quay lại 180 ngày",
  },
  {
    key: "birthday",
    delay: 0,
    priority: "low",
    mode: "staff_task",
    action: "Nhắn Zalo chúc mừng sinh nhật (gửi tay)",
    trigger: "Sinh nhật trong tuần",
  },
];

export const rules: S["CrmRuleOut"][] = RULE_SEEDS.map((r, i) => ({
  id: uuid(i + 1, 11),
  rule_key: r.key,
  name: r.trigger,
  trigger: r.trigger,
  delay_days: r.delay,
  priority: r.priority,
  send_mode: r.mode,
  suggested_action: r.action,
  active: true,
  conditions: {},
  version: 1,
}));
