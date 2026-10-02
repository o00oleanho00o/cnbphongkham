// Vietnamese words for the codes the care API sends. The codes (`reason`, `code`, enum values) are machine
// strings: they are looked up here and never shown raw; an unknown one reads as a generic phrase, so a code added
// by the backend before this table knows it does not leak into the screen.
import type { Schemas } from "@/lib/api";
import type {
  CareAlertKind,
  CareControlState,
  CareDepth,
  CareLevel,
  CareUrgency,
  DepthSignal,
  Weekday,
} from "@/lib/care/care-types";

export const DEPTH_LABEL: Record<CareDepth, string> = {
  D1: "D1 · Hành chính",
  D2: "D2 · Chăm sóc chuẩn",
  D3: "D3 · Triệu chứng nhẹ",
  D4: "D4 · Phán đoán y khoa",
  D5: "D5 · Dấu hiệu nguy hiểm",
};

export const LEVEL_LABEL: Record<CareLevel, string> = {
  L0: "L0 · Chỉ soạn nháp",
  L1: "L1 · Tin mẫu đã duyệt",
  L2: "L2 · Trả lời có nguồn",
};

export const URGENCY_LABEL: Record<CareUrgency, string> = {
  normal: "Thường",
  urgent: "Khẩn",
};

export const CONTROL_LABEL: Record<CareControlState, string> = {
  AUTO: "Agent phụ trách",
  HANDOFF_ROUTING: "Đang tìm người nhận",
  STAFF: "Nhân viên phụ trách",
};

export const SIGNAL_LABEL: Record<DepthSignal, string> = {
  default: "Mặc định",
  vip: "Khách VIP",
  complex_history: "Tiền sử phức tạp",
  past_complaint: "Từng khiếu nại",
  pending_doctor_work: "Đang chờ việc của bác sĩ",
  post_procedure: "Trong cửa sổ sau thủ thuật",
  out_of_hours: "Ngoài giờ làm việc",
  asks_for_human: "Khách muốn gặp người",
  negative_sentiment: "Khách bực bội",
  repeated_question: "Hỏi lặp lại",
  answer_rejected: "Câu trả lời trước bị từ chối",
  urgent: "Mức khẩn",
};

/** Why the agent asked for a person: the signals of the handoff skill plus the ones it handles itself. */
const REASON_LABEL: Record<string, string> = {
  ...SIGNAL_LABEL,
  default: "Câu hỏi vượt ngưỡng độ sâu",
  red_flag: "Dấu hiệu nguy hiểm (cờ đỏ)",
  low_confidence: "Agent chưa chắc câu trả lời",
  unverified: "Khách chưa xác minh danh tính",
  no_source: "Không có nguồn trong kho tri thức",
};

export function reasonLabel(code: string): string {
  return REASON_LABEL[code] ?? "Lý do khác";
}

const ACTION_TYPE_LABEL: Record<string, string> = {
  reminder_template: "Nhắc lịch theo mẫu",
  care_guide_template: "Hướng dẫn chăm sóc theo mẫu",
  appointment_confirm: "Xác nhận lịch hẹn",
  faq_kb_answer: "Trả lời từ kho tri thức",
  symptom_reply: "Phản hồi triệu chứng",
  medical_judgement: "Nhận định y khoa",
  birthday_greeting: "Chúc mừng sinh nhật",
};

export const ACTION_TYPES: readonly string[] = Object.keys(ACTION_TYPE_LABEL);

export function actionTypeLabel(actionType: string): string {
  return ACTION_TYPE_LABEL[actionType] ?? "Hành động khác";
}

const CODE_LABEL: Record<string, string> = {
  "control:auto_to_handoff_routing": "Agent nhờ người nhận cuộc trò chuyện",
  "control:handoff_routing_to_staff": "Nhân viên nhận cuộc trò chuyện",
  "control:handoff_routing_declined": "Một nhân viên từ chối nhận",
  "control:staff_to_auto": "Trả lại cho agent",
  "control:holding_message": "Gửi khách tin báo đã chuyển nhân viên",
  "control:holding_message_failed": "Gửi tin báo cho khách không thành công",
  "control:auto_release_after_set": "Đổi hẹn tự trả về agent",
  autonomy_change: "Đổi mức tự chủ của agent",
  "autonomy:override_set": "Đặt mức tự chủ tạm thời",
  "autonomy:override_cleared": "Hết mức tự chủ tạm thời",
  "autonomy:override_expired": "Hết mức tự chủ tạm thời",
};

function prefixesLongestFirst(code: string): string[] {
  const parts = code.split(":");
  return parts.map((_, i) => parts.slice(0, parts.length - i).join(":"));
}

/**
 * Words for an `action_type` code such as `control:auto_to_handoff_routing:agent` or `reminder_template:d3`:
 * the longest known prefix wins (the tail names the initiator or the reason, which the entry shows elsewhere).
 * `null` when no prefix is known.
 */
export function knownCodeLabel(code: string): string | null {
  const key = prefixesLongestFirst(code).find((k) => CODE_LABEL[k] ?? ACTION_TYPE_LABEL[k]);
  return key === undefined ? null : (CODE_LABEL[key] ?? ACTION_TYPE_LABEL[key] ?? null);
}

export function codeLabel(code: string): string {
  return knownCodeLabel(code) ?? "Hoạt động của agent";
}

export const ENTRY_KIND_LABEL: Record<Schemas["TimelineEntryKind"], string> = {
  sent: "Agent đã gửi",
  reviewed: "Người đã duyệt",
  paused: "Đang giữ lại",
  control: "Chuyển trạng thái",
  autonomy: "Mức tự chủ",
};

export const MEMORY_SOURCE_LABEL: Record<Schemas["MemorySourceOut"], string> = {
  patient: "Từ khách",
  staff: "Nhân viên dặn",
  doctor_edit: "Bác sĩ sửa",
};

export const ALERT_KIND_LABEL: Record<CareAlertKind, string> = {
  demotion: "Agent bị hạ mức tự chủ",
  unresponsive: "Khách không phản hồi nhiều lần",
  red_flag: "Cờ đỏ",
  on_call_used: "Đã dùng số trực 24/24",
};

export const WEEKDAY_LABEL: Record<Weekday, string> = {
  mon: "Thứ hai",
  tue: "Thứ ba",
  wed: "Thứ tư",
  thu: "Thứ năm",
  fri: "Thứ sáu",
  sat: "Thứ bảy",
  sun: "Chủ nhật",
};

const SKILL_LABEL: Record<string, string> = {
  general: "Chung",
  medical: "Y khoa (bác sĩ)",
  dat_lich: "Đặt lịch",
  thanh_toan: "Thanh toán",
  khieu_nai: "Khiếu nại",
  mun: "Mụn",
  nam: "Nám",
  laser: "Laser",
};

export function skillLabel(skill: string): string {
  return SKILL_LABEL[skill] ?? skill;
}

export const REVIEW_KIND_SHORT: Record<Schemas["ReviewKind"], string> = {
  reply_draft: "Nháp trả lời khách",
  followup_draft: "Nháp tin chăm sóc",
  triage_alert: "Cảnh báo cờ đỏ",
  media_flag: "Khách gửi ảnh hoặc tệp",
  identity_check: "Xác minh danh tính",
};
