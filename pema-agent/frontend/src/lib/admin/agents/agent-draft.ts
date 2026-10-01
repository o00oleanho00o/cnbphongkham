// ported from: web/src/pages/agent-draft.ts
//
// Deviations (forced by the new platform):
// - `DUONG_DAN_TAO` is "/admin/agents/new" (original "/agents/_new"). A Next.js App Router folder
//   whose name starts with an underscore is private (not routable), so the create route cannot be
//   "_new". The original's reason (the route must never hide a real agent id) is kept another way:
//   "new" matches the id regex, so `ID_DANH_RIENG` lists it and `kiemDinhDangId` refuses it as an
//   agent id. The BE should refuse it too (open item), otherwise an API-created "new" has no page.
// - react-router's `navigate(path, { state })` does not exist: the draft (and the one-off error
//   after a half-done create) travels through `sessionStorage`. Side effect: F5 on the create page
//   keeps the draft instead of losing it.
// - `BanNhapAgent` and the form carry `policyProfile` (new field, default `patient_channel`), and
//   POST accepts it, so it never forces the extra PATCH.

import type { AgentDetailForm } from "@/lib/admin/agents/agent-detail-form";
import { laHoSoChinhSach, type PolicyProfileKey } from "@/lib/admin/agents/agent-policy-profile";

/**
 * Bản nhập của màn "Tạo agent mới": modal chỉ thu thập rồi chuyển sang trang
 * tạo, KHÔNG ghi gì vào DB. Agent chỉ thật sự sinh ra khi bấm nút Tạo ở trang
 * đó - trước đó bấm Hủy là mất trắng, đúng nghĩa "chưa tạo".
 */
export type BanNhapAgent = {
  id: string;
  name: string;
  icon: string;
  persona: string;
  policyProfile: PolicyProfileKey;
};

/**
 * Đường dẫn trang tạo. Đây là một đoạn tĩnh nằm cạnh `[id]` nên nó THẮNG route
 * `[id]`: agent mang id trùng đoạn cuối này sẽ bị che mất và không còn đường
 * vào sửa. Bản gốc dùng "/agents/_new" (gạch dưới nên không bao giờ là id hợp
 * lệ); Next.js coi thư mục bắt đầu bằng gạch dưới là riêng tư, không thành
 * route, nên ở đây dùng "/admin/agents/new" và chặn id "new" bằng
 * `ID_DANH_RIENG` thay vì bằng regex.
 */
export const DUONG_DAN_TAO = "/admin/agents/new";

/** Đường dẫn danh sách agent - nơi mọi màn tạo/sửa quay về */
export const DUONG_DAN_DANH_SACH = "/admin/agents";

/** Id khớp regex của BE nhưng không được dùng làm id agent vì route tĩnh đã chiếm */
export const ID_DANH_RIENG: readonly string[] = ["new"];

export function laIdDanhRieng(id: string): boolean {
  return ID_DANH_RIENG.includes(id);
}

/** Bản nhập -> form của trang. Mọi ô override để rỗng = theo trang Cấu hình. */
export function tuBanNhap(banNhap: BanNhapAgent): AgentDetailForm {
  return {
    icon: banNhap.icon,
    name: banNhap.name,
    persona: banNhap.persona,
    policyProfile: banNhap.policyProfile,
    maxSteps: "",
    reasoningEffort: "",
    disabledTools: [],
    contextWindow: "",
  };
}

/**
 * Sau khi POST có cần PATCH thêm một nhịp không.
 *
 * `POST /admin/agents` chỉ nhận id/name/icon/persona/policy_profile
 * (`AgentCreate`), không nhận model override lẫn danh sách tool tắt. Ai chỉnh
 * mấy ô đó ngay ở màn tạo thì phải gửi tiếp một PATCH, còn để nguyên mặc định
 * thì một lần POST là xong - đây là ca thường gặp nên không bắn request thừa.
 */
export function canPatchSauKhiTao(form: AgentDetailForm): boolean {
  return (
    form.maxSteps.trim() !== "" ||
    form.reasoningEffort !== "" ||
    form.contextWindow.trim() !== "" ||
    form.disabledTools.length > 0
  );
}

/** Trùng id thì phải chặn NGAY ở modal: trang tạo mới báo thì đã gõ xong persona */
export function idDaCoRoi(id: string, idDangCo: string[]): boolean {
  return id !== "" && idDangCo.includes(id);
}

// --- Chuyền bản nhập giữa modal (trang danh sách) và trang tạo ---------------------------------

/** Chỉ cần hai hàm này của `Storage`, để test được mà không cần trình duyệt */
export type KhoTam = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const KHOA_BAN_NHAP = "pema:agent-ban-nhap";
const KHOA_LOI_SAU_KHI_TAO = "pema:agent-loi-sau-khi-tao";

/** `sessionStorage` của tab này, hoặc null khi trình duyệt chặn (chế độ riêng tư, SSR) */
export function khoTamCuaTab(): KhoTam | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export function luuBanNhap(kho: KhoTam | null, banNhap: BanNhapAgent): boolean {
  if (!kho) return false;
  try {
    kho.setItem(KHOA_BAN_NHAP, JSON.stringify(banNhap));
    return true;
  } catch {
    return false;
  }
}

function laBanNhap(v: unknown): v is BanNhapAgent {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.id === "string" &&
    o.id !== "" &&
    typeof o.name === "string" &&
    typeof o.icon === "string" &&
    typeof o.persona === "string" &&
    laHoSoChinhSach(o.policyProfile)
  );
}

/** Đọc bản nhập đang chờ; dữ liệu hỏng hoặc thiếu thì coi như không có (trang tạo đá về danh sách) */
export function docBanNhap(kho: KhoTam | null): BanNhapAgent | null {
  if (!kho) return null;
  try {
    const raw = kho.getItem(KHOA_BAN_NHAP);
    if (raw === null) return null;
    const v: unknown = JSON.parse(raw);
    return laBanNhap(v) ? v : null;
  } catch {
    return null;
  }
}

export function xoaBanNhap(kho: KhoTam | null): void {
  try {
    kho?.removeItem(KHOA_BAN_NHAP);
  } catch {
    // Không xóa được thì thôi: lần tạo sau ghi đè
  }
}

/**
 * Ca hiếm: agent đã tạo xong nhưng nhịp PATCH phần model hỏng - trang sửa phải
 * nói ra. Nhớ một lần duy nhất (đọc xong là xóa) để F5 không hiện lại câu cũ.
 */
export function luuLoiSauKhiTao(kho: KhoTam | null, loi: string): void {
  try {
    kho?.setItem(KHOA_LOI_SAU_KHI_TAO, loi);
  } catch {
    // Không lưu được thì trang sửa chỉ không hiện câu cảnh báo
  }
}

export function layLoiSauKhiTao(kho: KhoTam | null): string {
  try {
    const loi = kho?.getItem(KHOA_LOI_SAU_KHI_TAO) ?? "";
    if (loi !== "") kho?.removeItem(KHOA_LOI_SAU_KHI_TAO);
    return loi;
  } catch {
    return "";
  }
}
