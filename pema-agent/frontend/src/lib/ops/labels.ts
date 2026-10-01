// Vietnamese labels of the CRM and review enums. The wording is the one of the web prototype
// (prototype/shared/crm-automation.js and crm-ui.js) so staff see the same words in both products; the
// enum VALUES come from the OpenAPI contract and are never shown raw.
import type { Schemas } from "@/lib/api";

type S = Schemas;

export const RULE_LABEL: Record<S["RuleKey"], string> = {
  d1: "Sau thủ thuật · D+1",
  d3: "Ảnh tiến triển · D+3",
  d7: "Bác sĩ review · D+7",
  due: "Đến hạn tái khám",
  overdue: "Quá hạn tái khám",
  no_show: "Vắng hẹn",
  abandoned: "Tiếp tục liệu trình",
  dormant90: "Kết nối lại · 90 ngày",
  dormant180: "Kết nối lại · 180 ngày",
  birthday: "Sinh nhật trong tuần",
  manual: "Việc thủ công",
};

export const OUTCOME_LABEL: Record<S["CrmOutcome"], string> = {
  unanswered: "Không nghe máy",
  callback: "Gọi lại sau",
  no_need: "Đã liên hệ, chưa có nhu cầu",
  busy: "Đang bận, hẹn gọi lại",
  booked: "Đồng ý đặt lịch",
  doctor: "Muốn bác sĩ tư vấn",
  reaction: "Có phản hồi sau điều trị",
  complaint: "Khiếu nại",
  optout: "Không muốn nhận CSKH",
  invalid: "Sai số / không liên hệ được",
};

export const CHANNEL_LABEL: Record<S["CrmChannel"], string> = {
  call: "Gọi điện",
  zalo: "Zalo",
  sms: "SMS",
  internal_note: "Ghi chú nội bộ",
};

export const PRIORITY_LABEL: Record<S["TaskPriority"], string> = {
  high: "Cao",
  normal: "Bình thường",
  low: "Thấp",
};

export const TASK_STATUS_LABEL: Record<S["TaskStatus"], string> = {
  open: "Cần làm",
  rescheduled: "Hẹn lại",
  resolved: "Đã xử lý",
  superseded: "Đã thay thế",
};

export const APPOINTMENT_STATUS_LABEL: Record<S["AppointmentStatus"], string> = {
  booked: "Đặt hẹn",
  confirmed: "Đã xác nhận",
  arrived: "Đang chờ",
  in_progress: "Đang điều trị",
  completed: "Hoàn tất",
  cancelled: "Đã hủy",
  missed: "Vắng hẹn",
};

export const CONVERSATION_STATUS_LABEL: Record<S["ConversationStatus"], string> = {
  open: "Đang mở",
  pending_review: "Chờ duyệt",
  handoff: "Chuyển nhân viên",
  closed: "Đã đóng",
};

export const REVIEW_KIND_LABEL: Record<S["ReviewKind"], string> = {
  reply_draft: "Nháp trả lời",
  followup_draft: "Nháp chăm sóc sau điều trị",
  triage_alert: "Cảnh báo cần bác sĩ",
  media_flag: "Khách gửi ảnh hoặc tệp",
  identity_check: "Xác minh danh tính",
};

export const REVIEW_STATUS_LABEL: Record<S["ReviewStatus"], string> = {
  pending: "Chờ duyệt",
  approved: "Đã duyệt",
  rejected: "Đã từ chối",
  escalated: "Đã chuyển bác sĩ",
  expired: "Hết hạn",
};

export const REVIEW_ORIGIN_LABEL: Record<S["ReviewOrigin"], string> = {
  agent_turn: "Trợ lý AI trả lời khách",
  scheduled_agent: "Trợ lý AI theo lịch",
  crm_rule: "Quy tắc chăm sóc",
  policy: "Hồ sơ chính sách",
};

export const RISK_LABEL: Record<S["RiskLevel"], string> = {
  normal: "Bình thường",
  attention: "Cần chú ý",
  red_flag: "Dấu hiệu cần bác sĩ",
};

export const LIFECYCLE_LABEL: Record<string, string> = {
  new: "Khách mới",
  returning: "Khách quay lại",
  treating: "Đang điều trị",
  dormant: "Lâu chưa quay lại",
  reactivated: "Đã quay lại sau CSKH",
};

export const EXPECTED_SOURCE_LABEL: Record<string, string> = {
  doctor_recommendation: "Bác sĩ khuyến nghị",
  service_protocol: "Protocol dịch vụ",
  treatment_plan: "Kế hoạch điều trị",
  appointment: "Lịch đã đặt",
  followup_automation: "Chăm sóc sau điều trị",
};

export const CONSENT_KIND_LABEL: Record<S["ConsentKind"], string> = {
  messaging: "Nhận tin chăm sóc",
  marketing: "Nhận tin quảng bá",
  media: "Sử dụng hình ảnh",
  data_processing: "Xử lý dữ liệu cá nhân",
};

export const GENDER_LABEL: Record<S["Gender"], string> = {
  female: "Nữ",
  male: "Nam",
  other: "Khác",
  unknown: "Chưa rõ",
};

export const SENDER_LABEL: Record<S["SenderType"], string> = {
  patient: "Khách",
  staff: "Nhân viên",
  ai_draft: "Trợ lý AI (nháp)",
  system: "Hệ thống",
};

export const MESSAGE_STATUS_LABEL: Record<S["MessageStatus"], string> = {
  received: "Đã nhận",
  draft: "Nháp chờ duyệt",
  queued: "Đang gửi",
  sent: "Đã gửi",
  failed: "Gửi lỗi",
  rejected: "Đã từ chối",
};

export const CHANNEL_KIND_LABEL: Record<S["ChannelKind"], string> = {
  zalo_bot: "Zalo Bot",
  zalo_personal: "Zalo cá nhân",
  zalo_oa: "Zalo OA",
};

export const POLICY_PROFILE_LABEL: Record<S["PolicyProfileKey"], string> = {
  staff_assistant: "Trợ lý nội bộ",
  patient_channel: "Kênh bệnh nhân",
};
