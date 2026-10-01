// New in Pema (no zalo-agent original): the Vietnamese wording of the two policy profiles of
// PLAN-AI01 section 5, shown in the account drawer and as a badge on each account card. The rules
// themselves are the backend's (`pema.policy`); this file only explains them to the operator.
import type { Schemas } from "@/lib/api";

type PolicyProfileKey = Schemas["PolicyProfileKey"];

/** Hồ sơ mặc định của mọi account và agent mới (fail safe, CONTRACTS-AI01 section 7.2). */
export const HO_SO_MAC_DINH: PolicyProfileKey = "patient_channel";

export const NHAN_HO_SO: Record<PolicyProfileKey, string> = {
  patient_channel: "Kênh bệnh nhân",
  staff_assistant: "Trợ lý nhân viên",
};

/** Hai câu giải thích mỗi hồ sơ, mỗi câu một dòng. */
export const MO_TA_HO_SO: Record<PolicyProfileKey, readonly [string, string]> = {
  patient_channel: [
    "Mọi tin gửi đi vào hàng đợi duyệt để một người duyệt rồi mới gửi; ca cờ đỏ (chảy máu, sốt, mưng mủ, khó thở) chuyển bác sĩ trước khi gọi mô hình AI.",
    "Số điện thoại, CCCD, email bị che trước khi gửi cho mô hình; công cụ ảnh, video, tài liệu và web bị tắt.",
  ],
  staff_assistant: [
    "Hành vi nguyên bản của trợ lý nội bộ: AI trả lời và GỬI THẲNG cho người nhận, không qua hàng đợi duyệt.",
    "Không tự chuyển bác sĩ khi có cờ đỏ, chỉ che thông tin cá nhân khi bật tùy chọn; công cụ ảnh, video, tài liệu, web theo cấu hình agent.",
  ],
};

export const CANH_BAO_HO_SO =
  "Account nhắn tin với BỆNH NHÂN phải ở hồ sơ Kênh bệnh nhân. Chỉ dùng Trợ lý nhân viên cho account " +
  "nội bộ chỉ có nhân viên. Mặc định là Kênh bệnh nhân.";

/** Cảnh báo riêng khi người dùng đang chuyển một account sang hồ sơ gửi thẳng. */
export const CANH_BAO_CHUYEN_SANG_TRO_LY =
  "Chuyển sang Trợ lý nhân viên: tin của account này sẽ được gửi thẳng, không qua người duyệt.";
