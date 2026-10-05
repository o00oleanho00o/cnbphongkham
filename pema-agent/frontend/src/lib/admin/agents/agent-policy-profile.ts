// NEW (no zalo-agent original): the policy profile of an agent, PLAN-AI01 section 5.
//
// The profile is a safety setting, not a feature switch: `patient_channel` is the restrictive default
// for anything that talks to patients, `staff_assistant` keeps the original zalo-agent behaviour for
// an internal helper. The BE enforces it (review queue, red flags, PII masking, tool blocking); this
// file only holds the labels and the explanation shown next to the choice, so the create modal, the
// detail form and the agent card say the same thing.
import type { Schemas } from "@/lib/api";

export type PolicyProfileKey = Schemas["PolicyProfileKey"];

/** Restrictive profile first: it is the BE default and the one that wins over the account's. */
export const HO_SO_MAC_DINH: PolicyProfileKey = "patient_channel";

export const THU_TU_HO_SO: readonly PolicyProfileKey[] = ["patient_channel", "staff_assistant"];

export const NHAN_HO_SO: Record<PolicyProfileKey, string> = {
  patient_channel: "Kênh bệnh nhân",
  staff_assistant: "Trợ lý nội bộ",
};

/** Hai dòng giải thích của mỗi hồ sơ - người vận hành đọc để biết chọn cái nào */
export const MO_TA_HO_SO: Record<PolicyProfileKey, readonly [string, string]> = {
  patient_channel: [
    "Tin gửi ra ngoài vào hàng đợi duyệt để một người bấm gửi; dấu hiệu cờ đỏ chuyển bác sĩ trước khi gọi model.",
    "Thông tin cá nhân được che; công cụ ảnh, video, tài liệu, web tắt; save_memory tắt với nội dung từ bệnh nhân.",
  ],
  staff_assistant: [
    "Giữ hành vi gốc của agent: tin gửi thẳng, không qua hàng đợi duyệt.",
    "Chỉ dùng cho trợ lý của nhân viên, không dùng để trả lời bệnh nhân.",
  ],
};

/** Câu chung dưới ô chọn: khi agent và tài khoản khai hai hồ sơ khác nhau */
export const GHI_CHU_HO_SO_THANG =
  "Khi agent gắn vào một tài khoản, hồ sơ nghiêm hơn (của agent hoặc của tài khoản) sẽ được áp dụng.";

export function laHoSoChinhSach(value: unknown): value is PolicyProfileKey {
  return value === "patient_channel" || value === "staff_assistant";
}
