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

// ---------------------------------------------------------------- Patient 360 tabs (package U, step U3)

export const PLAN_STATUS_LABEL: Record<S["PlanStatus"], string> = {
  planned: "Dự kiến",
  active: "Đang thực hiện",
  completed: "Đã đủ buổi",
  abandoned: "Bỏ dở",
  cancelled: "Đã hủy",
};

export const MEDIA_STAGE_LABEL: Record<S["MediaStage"], string> = {
  before: "Trước điều trị",
  after: "Sau điều trị",
};

/** `session-type` options of the old form: the plan's own procedure first, then these two. */
export const EXTRA_SESSION_TYPES = ["Tái khám đánh giá", "Chăm sóc phục hồi"] as const;
/** `session-region` and `session-view` options of the old form. */
export const PHOTO_REGIONS = ["Mặt", "Cổ", "Vùng khác"] as const;
export const PHOTO_VIEWS = ["Chính diện", "Má trái", "Má phải"] as const;

export const LASER_PROTOCOL_ID = "laser-co2";
/** `session-protocol` options of the old form: "" = as the doctor recommends. */
export const PROTOCOL_OPTIONS: readonly { value: string; label: string }[] = [
  { value: "", label: "Theo khuyến nghị bác sĩ" },
  { value: LASER_PROTOCOL_ID, label: "Laser CO2 · D+1 / D+3 / D+7 / D+30" },
];
