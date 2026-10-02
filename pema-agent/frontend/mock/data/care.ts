// Fictional state of the care-agent supervision screens (package M, step M5): rounds waiting for a person,
// patients whose conversation a person holds, timelines, agent memory, staff skills and shifts, the 24/7 contact
// (a FIXTURE number, never a real one), the matrix and the alerts. Names come from the synthetic set of
// `data/clinic.ts`; there is no real record, phone number or message text here.
import { USERS } from "../auth";
import { DAY, HOUR, MIN, isoFromNow, uuid, type Schemas } from "../core";
import { patientRef } from "./clinic";

type S = Schemas;

export const BASE_LEVEL: Record<string, S["CareLevel"]> = {};
export const MAX_OVERRIDE_DAYS = 30;

const CS_MAI_ANH = uuid(4, 1);
const CS_THU = uuid(6, 1);
const OWNER = uuid(1, 1);
const DOCTOR_TAM = uuid(3, 1);

export type MockRound = {
  patientId: string;
  reason: string;
  summary: string;
  depth: S["CareDepth"];
  urgency: S["CareUrgency"];
  confidence: number;
  requiredSkill: string | null;
  openedAt: string;
  slaDueAt: string | null;
  /** user ids in order; null is the 24/7 on-call contact (always last) */
  chain: (string | null)[];
  idx: number;
  suggestedBy: string | null;
};

export type MockControl = {
  state: S["CareControlState"];
  since: string;
  ownerId: string | null;
  note: string | null;
};

export type MockEntry = S["TimelineEntryOut"];

export type MockOverride = { level: S["CareLevel"]; until: string } | null;

const p = (n: number) => patientRef(n);

export const rounds: MockRound[] = [
  {
    patientId: p(2).id,
    reason: "asks_for_human",
    summary:
      "Khách hỏi lại lần thứ hai về lịch tái khám sau laser và nói muốn gặp nhân viên. Chưa có dấu hiệu bất thường.",
    depth: "D2",
    urgency: "normal",
    confidence: 0.72,
    requiredSkill: "dat_lich",
    openedAt: isoFromNow(-6 * MIN),
    slaDueAt: isoFromNow(24 * MIN),
    chain: [CS_MAI_ANH, CS_THU, null],
    idx: 0,
    suggestedBy: null,
  },
  {
    patientId: p(3).id,
    reason: "negative_sentiment",
    summary:
      "Khách phàn nàn về thời gian chờ buổi hẹn trước và hỏi về hoàn phí. Giọng điệu không hài lòng.",
    depth: "D3",
    urgency: "normal",
    confidence: 0.81,
    requiredSkill: "khieu_nai",
    openedAt: isoFromNow(-18 * MIN),
    slaDueAt: isoFromNow(12 * MIN),
    chain: [CS_MAI_ANH, OWNER, null],
    idx: 0,
    suggestedBy: null,
  },
  {
    patientId: p(5).id,
    reason: "red_flag",
    summary:
      "Khách báo sưng tăng và đau nhiều sau thủ thuật hôm qua. Cờ đỏ được phát hiện trước khi gọi mô hình.",
    depth: "D5",
    urgency: "urgent",
    confidence: 0.95,
    requiredSkill: "medical",
    openedAt: isoFromNow(-2 * MIN),
    slaDueAt: isoFromNow(3 * MIN),
    chain: [DOCTOR_TAM, null],
    idx: 0,
    suggestedBy: null,
  },
  {
    patientId: p(6).id,
    reason: "default",
    summary: "Khách hỏi về tác dụng phụ của thuốc đang dùng. Hai người đầu chuỗi chưa phản hồi.",
    depth: "D4",
    urgency: "urgent",
    confidence: 0.88,
    requiredSkill: "medical",
    openedAt: isoFromNow(-41 * MIN),
    slaDueAt: null,
    chain: [DOCTOR_TAM, null],
    idx: 1,
    suggestedBy: "BS. Lê Minh Tâm",
  },
];

export const controls = new Map<string, MockControl>([
  [
    p(7).id,
    {
      state: "STAFF",
      since: isoFromNow(-2 * HOUR),
      ownerId: CS_MAI_ANH,
      note: null,
    },
  ],
  [
    p(8).id,
    {
      state: "STAFF",
      since: isoFromNow(-26 * HOUR),
      ownerId: DOCTOR_TAM,
      note: null,
    },
  ],
]);

BASE_LEVEL[p(1).id] = "L2";
BASE_LEVEL[p(7).id] = "L2";
BASE_LEVEL[p(8).id] = "L1";

export const overrides = new Map<string, MockOverride>([
  [p(1).id, { level: "L0", until: isoFromNow(3 * DAY) }],
]);

function entry(
  id: string,
  at: number,
  kind: S["TimelineEntryKind"],
  code: string,
  extra: Partial<MockEntry> = {},
): MockEntry {
  return { id, at: isoFromNow(at), kind, code, ...extra };
}

export const entries = new Map<string, MockEntry[]>([
  [
    p(1).id,
    [
      entry("e1-1", -3 * DAY, "autonomy", "autonomy_change:override_set:L0", {
        detail: "Hạ mức có thời hạn khi trả lại cho agent.",
      }),
      entry("e1-2", -2 * HOUR, "sent", "reminder_template:d3", { depth: "D1" }),
      entry("e1-3", -26 * HOUR, "reviewed", "faq_kb_answer", {
        depth: "D2",
        actor_name: "Mai Anh",
        detail: "Duyệt, không sửa.",
      }),
    ],
  ],
  [
    p(2).id,
    [
      entry("e2-1", -6 * MIN, "control", "control:auto_to_handoff_routing:agent", { depth: "D2" }),
      entry("e2-2", -6 * MIN, "sent", "control:holding_message", { depth: "D2" }),
      entry("e2-3", -5 * DAY, "sent", "appointment_confirm", { depth: "D1" }),
    ],
  ],
  [
    p(7).id,
    [
      entry("e7-1", -2 * HOUR, "control", "control:handoff_routing_to_staff:staff", {
        actor_name: "Mai Anh",
      }),
      entry("e7-2", -3 * HOUR, "control", "control:auto_to_handoff_routing:agent", { depth: "D3" }),
      entry("e7-3", -3 * HOUR, "paused", "reminder_template:due"),
      entry("e7-4", -1 * DAY, "sent", "care_guide_template", { depth: "D1" }),
    ],
  ],
  [
    p(8).id,
    [
      entry("e8-1", -26 * HOUR, "control", "control:handoff_routing_to_staff:staff", {
        actor_name: "BS. Lê Minh Tâm",
      }),
      entry("e8-2", -27 * HOUR, "control", "control:auto_to_handoff_routing:agent", {
        depth: "D5",
      }),
    ],
  ],
]);

export const pendingDrafts = new Map<string, S["PendingDraftOut"][]>([
  [
    p(2).id,
    [
      {
        review_item_id: uuid(401, 3),
        kind: "reply_draft",
        created_at: isoFromNow(-5 * MIN),
        requires_doctor: false,
      },
    ],
  ],
  [
    p(5).id,
    [
      {
        review_item_id: uuid(402, 3),
        kind: "triage_alert",
        created_at: isoFromNow(-2 * MIN),
        requires_doctor: true,
      },
    ],
  ],
]);

export const pausedReminders = new Map<string, S["PausedReminderOut"][]>([
  [
    p(7).id,
    [
      {
        id: uuid(501, 4),
        event_kind: "reminder_due",
        due_at: isoFromNow(-3 * HOUR),
        paused_at: isoFromNow(-3 * HOUR),
        prepared_text: "Chào anh/chị, đến hẹn tái khám theo lịch. Anh/chị muốn đặt giờ nào ạ?",
      },
    ],
  ],
]);

export const memory = new Map<string, S["MemoryFactOut"][]>([
  [
    p(1).id,
    [
      {
        id: uuid(601, 5),
        fact: "Khách thích nhận tin vào buổi tối, sau 18 giờ.",
        source: "patient",
        created_at: isoFromNow(-40 * DAY),
        valid_until: null,
      },
      {
        id: uuid(602, 5),
        fact: "Gọi khách bằng chị, không dùng tên riêng.",
        source: "staff",
        created_at: isoFromNow(-12 * DAY),
        valid_until: null,
      },
    ],
  ],
  [p(7).id, []],
]);

// ------------------------------------------------------------------------------------- admin
type ShiftDays = S["ShiftOut"];

function office(): ShiftDays {
  const day = [{ start: "08:00" as const, end: "17:00" as const }];
  return { mon: day, tue: day, wed: day, thu: day, fri: day, sat: [], sun: [] };
}

function morning(): ShiftDays {
  const day = [{ start: "08:00" as const, end: "12:00" as const }];
  return { mon: day, tue: day, wed: day, thu: day, fri: day, sat: day, sun: [] };
}

export type MockStaffProfile = {
  userId: string;
  skills: string[];
  shift: ShiftDays;
  capacity: number;
  languages: string[];
  version: number;
};

export const staffProfiles: MockStaffProfile[] = [
  {
    userId: CS_MAI_ANH,
    skills: ["dat_lich", "khieu_nai", "thanh_toan"],
    shift: office(),
    capacity: 6,
    languages: ["vi"],
    version: 1,
  },
  {
    userId: CS_THU,
    skills: ["dat_lich", "mun", "nam"],
    shift: morning(),
    capacity: 5,
    languages: ["vi", "en"],
    version: 1,
  },
  {
    userId: DOCTOR_TAM,
    skills: ["medical", "laser", "mun"],
    shift: office(),
    capacity: 3,
    languages: ["vi"],
    version: 1,
  },
  {
    userId: OWNER,
    skills: ["khieu_nai"],
    shift: office(),
    capacity: 2,
    languages: ["vi"],
    version: 1,
  },
];

export const KNOWN_SKILLS = [
  "general",
  "medical",
  "dat_lich",
  "thanh_toan",
  "khieu_nai",
  "mun",
  "nam",
  "laser",
];

export const onCall: S["OnCallContactOut"][] = [
  {
    id: uuid(701, 6),
    // A FIXTURE number (reserved range), flagged `is_fixture`: never a real contact.
    zalo_number: "0000000001",
    owner: "Điều dưỡng trực (mẫu)",
    valid_from: isoFromNow(-30 * DAY),
    valid_to: null,
    active: true,
    is_fixture: true,
    version: 1,
  },
];

export const matrix: {
  pending: boolean;
  version: number;
  handoff: S["HandoffMatrixOut"];
  autonomy: S["AutonomyMatrixOut"];
} = {
  pending: true,
  version: 1,
  handoff: {
    confidence_threshold: 0.6,
    unverified_max_depth: "D1",
    post_procedure_window_hours: 48,
    repeat_question_threshold: 2,
    rows: [
      { signal: "default", from_depth: "D4" },
      { signal: "vip", from_depth: "D2" },
      { signal: "complex_history", from_depth: "D3" },
      { signal: "past_complaint", from_depth: "D3" },
      { signal: "pending_doctor_work", from_depth: "D3" },
      { signal: "post_procedure", from_depth: "D3" },
      { signal: "out_of_hours", from_depth: "D3" },
      { signal: "asks_for_human", from_depth: "D2" },
      { signal: "negative_sentiment", from_depth: "D2" },
      { signal: "repeated_question", from_depth: "D2" },
      { signal: "answer_rejected", from_depth: "D2" },
      { signal: "urgent", from_depth: "D4" },
    ],
  },
  autonomy: {
    confidence_threshold: 0.85,
    appointment_confirm_l1: false,
    rules: [
      { action_type: "reminder_template", hard_human: false, n_to_l2: null, d3_enabled: false },
      { action_type: "care_guide_template", hard_human: false, n_to_l2: null, d3_enabled: false },
      { action_type: "appointment_confirm", hard_human: false, n_to_l2: null, d3_enabled: false },
      { action_type: "faq_kb_answer", hard_human: false, n_to_l2: 10, d3_enabled: false },
      { action_type: "symptom_reply", hard_human: false, n_to_l2: null, d3_enabled: false },
      { action_type: "medical_judgement", hard_human: true, n_to_l2: null, d3_enabled: false },
      { action_type: "birthday_greeting", hard_human: true, n_to_l2: null, d3_enabled: false },
    ],
  },
};

export const timing: {
  sla_urgent_minutes: number;
  sla_normal_minutes: number;
  max_candidates: number;
  oncall_direct_from_depth: S["CareDepth"];
  version: number;
} = {
  sla_urgent_minutes: 5,
  sla_normal_minutes: 30,
  max_candidates: 5,
  oncall_direct_from_depth: "D3",
  version: 1,
};

export const alerts: S["CareAlertOut"][] = [
  {
    id: "a-1",
    kind: "red_flag",
    at: isoFromNow(-2 * MIN),
    patient_id: p(5).id,
    patient_name: p(5).full_name,
    code: "red_flag",
  },
  {
    id: "a-2",
    kind: "on_call_used",
    at: isoFromNow(-41 * MIN),
    patient_id: p(6).id,
    patient_name: p(6).full_name,
    code: "oncall:handoff",
  },
  {
    id: "a-3",
    kind: "demotion",
    at: isoFromNow(-3 * DAY),
    patient_id: p(1).id,
    patient_name: p(1).full_name,
    code: "autonomy_change:serious_edit",
  },
  {
    id: "a-4",
    kind: "unresponsive",
    at: isoFromNow(-1 * DAY),
    patient_id: p(9).id,
    patient_name: p(9).full_name,
    code: "no_reply_3",
  },
];

export function userName(userId: string | null): string | null {
  if (userId === null) return null;
  return USERS.find((u) => u.id === userId)?.display_name ?? null;
}
