// Fictional clinic data for the operations screens (patients, tasks, appointments, CRM rules).
// Names come from the synthetic set already in the repo (prototype/shared); there is no real record, phone
// number, photo or token here. Times are relative to "now" so "Việc hôm nay" always has work to show.
import { USERS } from "../auth";
import { DAY, HOUR, isoFromNow, uuid, type Schemas } from "../core";
import { ROOM_IDS } from "./catalog";

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

export const OWNER_NAMES: Record<string, string> = Object.fromEntries(
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
  room_id: null,
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
  room: string | null = null,
): S["AppointmentOut"] => {
  const at = `${clinicToday(dayOffset)}T${clock}:00+07:00`;
  return {
    ...appointment(n, patient, 0, status, note),
    doctor_id: doctor,
    room_id: room,
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
  // Rooms: most visits hold one (the room grid), visit 10 does not ("Chưa xếp phòng").
  onDay(6, 2, 0, "08:00", DOCTOR_AN, "completed", "Tái khám sau peel", 30, ROOM_IDS[0]),
  onDay(7, 3, 0, "08:30", DOCTOR_TAM, "in_progress", "Laser CO2 buổi 2/4", 45, ROOM_IDS[2]),
  onDay(8, 5, 0, "09:00", DOCTOR_AN, "arrived", "Tư vấn da liễu", 30, ROOM_IDS[0]),
  onDay(9, 7, 0, "09:30", DOCTOR_MAI, "confirmed", "Chăm sóc theo chỉ định", 45, ROOM_IDS[3]),
  onDay(10, 8, 0, "10:00", DOCTOR_TAM, "booked", "Tái khám"),
  onDay(11, 9, 0, "10:30", DOCTOR_AN, "missed", "Tái khám", 30, ROOM_IDS[1]),
  onDay(12, 10, 0, "14:00", DOCTOR_MAI, "booked", "Tư vấn chuyên sâu", 45, ROOM_IDS[1]),
  onDay(13, 6, 0, "15:00", DOCTOR_TAM, "cancelled", "Laser theo chỉ định", 45, ROOM_IDS[2]),
  onDay(14, 1, 1, "09:00", DOCTOR_TAM, "confirmed", "Buổi 3/4 Laser CO2", 45, ROOM_IDS[2]),
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

// ---------------------------------------------------------------- CRM rules

type RuleSeed = {
  key: S["RuleKey"];
  delay: number;
  priority: S["TaskPriority"];
  action: string;
  trigger: string;
};

const RULE_SEEDS: RuleSeed[] = [
  {
    key: "d1",
    delay: 1,
    priority: "high",
    action: "Nhắn Zalo hỏi thăm sau thủ thuật",
    trigger: "Một ngày sau thủ thuật có protocol",
  },
  {
    key: "d3",
    delay: 3,
    priority: "normal",
    action: "Nhắn Zalo nhắc khách gửi ảnh tiến triển",
    trigger: "Ba ngày sau thủ thuật",
  },
  {
    key: "d7",
    delay: 7,
    priority: "high",
    action: "Chuyển bác sĩ xem ảnh tiến triển D+7",
    trigger: "Bảy ngày sau thủ thuật",
  },
  {
    key: "due",
    delay: 0,
    priority: "normal",
    action: "Gọi nhắc lịch tái khám đã đến hạn",
    trigger: "Ngày dự kiến tái khám",
  },
  {
    key: "overdue",
    delay: 7,
    priority: "high",
    action: "Gọi hỏi lý do chưa tái khám",
    trigger: "Quá hạn tái khám 7 ngày",
  },
  {
    key: "no_show",
    delay: 1,
    priority: "high",
    action: "Gọi hỏi thăm và hỗ trợ đặt lại lịch",
    trigger: "Vắng hẹn",
  },
  {
    key: "abandoned",
    delay: 14,
    priority: "normal",
    action: "Nhắn Zalo nhắc tiếp tục liệu trình",
    trigger: "Còn buổi chưa làm sau 14 ngày",
  },
  {
    key: "dormant90",
    delay: 90,
    priority: "low",
    action: "Gọi kết nối lại",
    trigger: "Chưa quay lại 90 ngày",
  },
  {
    key: "dormant180",
    delay: 180,
    priority: "low",
    action: "Gọi kết nối lại",
    trigger: "Chưa quay lại 180 ngày",
  },
  {
    key: "birthday",
    delay: 0,
    priority: "low",
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
  suggested_action: r.action,
  active: true,
  conditions: {},
  version: 1,
}));
