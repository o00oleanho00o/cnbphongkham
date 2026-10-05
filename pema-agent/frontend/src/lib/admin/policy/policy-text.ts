// Vietnamese wording of the policy profile fields (`GET /admin/policy/profiles`). The profiles are DATA
// from the backend (PLAN-AI01 section 5); this file only turns each field into a sentence for the
// comparison table, so the table cannot drift from what the backend enforces: a new field value without a
// sentence shows as the raw value instead of silently disappearing.
import type { Schemas } from "@/lib/api";

type Profile = Schemas["PolicyProfile"];

export type PolicyRow = { key: string; label: string; text: (p: Profile) => string };

const OUTBOUND: Record<Profile["outbound_mode"], string> = {
  direct: "Gửi thẳng cho khách",
  review: "Vào hàng đợi duyệt, một người duyệt rồi mới gửi",
};

const SCHEDULED: Record<Profile["scheduled_jobs"], string> = {
  any: "Cho phép tin có sẵn và job chạy agent",
  message_from_template_only: "Chỉ tin từ mẫu bác sĩ đã duyệt; job agent chỉ soạn nháp",
};

const MEMORY: Record<Profile["memory_write"], string> = {
  allow: "Cho phép ghi nhớ",
  staff_only: "Tắt với nội dung từ bệnh nhân; chỉ bác sĩ hoặc CSKH ghi",
};

const MEDIA: Record<Profile["inbound_media"], string> = {
  pass: "Xử lý bình thường",
  flag_and_hand_off: "Gắn cờ Inbox và chuyển nhân viên; không phân tích ảnh",
};

const PII: Record<Profile["pii_mask"], string> = {
  off: "Không che",
  optional: "Che tùy chọn",
  required: "Bắt buộc che trước mọi lời gọi mô hình",
};

const CAP: Record<Profile["proactive_cap_scope"], string> = {
  account_thread: "Theo từng cuộc trò chuyện mỗi ngày",
  patient_account: "Theo từng bệnh nhân và tài khoản mỗi ngày",
};

const yesNo = (value: boolean, yes: string, no: string): string => (value ? yes : no);

export const POLICY_ROWS: PolicyRow[] = [
  { key: "outbound", label: "Tin gửi ra khách", text: (p) => OUTBOUND[p.outbound_mode] },
  { key: "scheduled", label: "Tin theo lịch", text: (p) => SCHEDULED[p.scheduled_jobs] },
  { key: "memory", label: "Ghi nhớ (save_memory)", text: (p) => MEMORY[p.memory_write] },
  { key: "media", label: "Ảnh khách gửi", text: (p) => MEDIA[p.inbound_media] },
  {
    key: "tools",
    label: "Công cụ ảnh, video, tài liệu, web",
    text: (p) =>
      (p.disabled_tool_keys ?? []).length > 0
        ? `Tắt (${(p.disabled_tool_keys ?? []).length} công cụ)`
        : "Theo cấu hình từng tài khoản",
  },
  {
    key: "redflag",
    label: "Cờ đỏ (chảy máu, sốt, mưng mủ, khó thở)",
    text: (p) => yesNo(p.red_flag_check, "Chuyển bác sĩ trước khi gọi mô hình", "Không áp dụng"),
  },
  { key: "pii", label: "Che thông tin cá nhân", text: (p) => PII[p.pii_mask] },
  { key: "cap", label: "Trần tin chủ động", text: (p) => CAP[p.proactive_cap_scope] },
  {
    key: "optout",
    label: "Khách từ chối tin quảng bá",
    text: (p) => yesNo(p.marketing_opt_out_blocks_marketing, "Chặn tin quảng bá", "Không chặn"),
  },
  {
    key: "birthday",
    label: "Sinh nhật",
    text: (p) => yesNo(p.birthday_auto_send, "Tự động gửi", "Không tự gửi, là việc của nhân viên"),
  },
  {
    key: "identity",
    label: "Xác minh danh tính Zalo với hồ sơ",
    text: (p) =>
      yesNo(
        p.require_identity_verification,
        "Bắt buộc trước khi nhắc tên, lịch hẹn hay thuốc",
        "Không cần",
      ),
  },
];
