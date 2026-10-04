// ported from: web/src/pages/agent-detail-form.ts
//
// Deviations: DTOs are the contract's snake_case `AgentOut` / `AgentUpdate`; the form and the PATCH body
// carry the new `policy_profile`. The original sent `modelProvider/modelName: null` on every save to clear
// old overrides; the contract has the explicit `clear_model_override` flag for that, sent instead.

type AgentOut = Schemas["AgentOut"];
type AgentUpdate = Schemas["AgentUpdate"];
type ReasoningEffort = Schemas["ReasoningEffort"];

import type { Schemas } from "@/lib/api";
import { HO_SO_MAC_DINH } from "@/lib/admin/agents/agent-policy-profile";
import type { AgentIdentityForm } from "@/components/admin/agents/agent-identity-section";
import { kiemSoBuoc, kiemTranContext } from "@/lib/admin/agents/agent-field-validators";
import type { AgentModelForm } from "@/components/admin/agents/agent-model-section";

/**
 * Ánh xạ giữa bản ghi agent và trạng thái form của trang sửa.
 *
 * Tách khỏi component vì đây là logic thuần, không dính React - và vì hai chiều
 * chuyển đổi phải soi gương nhau: chỗ nào `null` thành `""` lúc đọc thì lúc ghi
 * phải trả về `null`. Để lẫn trong component thì hai chiều dễ trôi khỏi nhau.
 */
export type AgentDetailForm = AgentIdentityForm &
  AgentModelForm & { disabledTools: string[]; contextWindow: string };

/**
 * Nhận cả bản ghi KHÔNG có `accountCount` (response của PATCH trả bản ghi thô,
 * chỉ `list()` mới cộng cột đó) - hàm này không đụng tới trường đó, bắt buộc nó
 * chỉ tổ ép caller bịa ra một con số.
 */
export function tuAgent(a: Omit<AgentOut, "account_count">): AgentDetailForm {
  return {
    icon: a.icon,
    name: a.name,
    persona: a.persona ?? "",
    policyProfile: a.policy_profile ?? HO_SO_MAC_DINH,
    // Chuỗi rỗng = "theo cấu hình chung"; gửi lên thành null
    maxSteps: a.max_steps == null ? "" : String(a.max_steps),
    reasoningEffort: a.reasoning_effort ?? "",
    // Sắp xếp để so sánh dirty bằng JSON.stringify không phụ thuộc thứ tự tick
    disabledTools: [...(a.disabled_tools ?? [])].sort(),
    contextWindow: a.context_window == null ? "" : String(a.context_window),
  };
}

/** Form -> body PATCH. Chuỗi rỗng thành `null` = bỏ override, theo cấu hình chung. */
export function thanhPatch(form: AgentDetailForm): AgentUpdate {
  const soBuoc = form.maxSteps.trim();
  return {
    icon: form.icon,
    name: form.name.trim(),
    persona: form.persona,
    policy_profile: form.policyProfile,
    // LUÔN xóa override: hai ô nhà cung cấp và model đã gỡ khỏi giao diện (xem agent-model-section.tsx),
    // agent luôn dùng cấu hình chung. Cờ này dọn ngay lần Lưu kế tiếp bản ghi cũ còn giá trị - bỏ qua thì
    // nó nằm lại trong DB, vẫn tác động bot mà không còn ô nào sửa được.
    clear_model_override: true,
    max_steps: soBuoc === "" ? null : Number(soBuoc),
    reasoning_effort:
      form.reasoningEffort === "" ? null : (form.reasoningEffort as ReasoningEffort),
    disabled_tools: form.disabledTools,
    context_window: form.contextWindow.trim() === "" ? null : Number(form.contextWindow.trim()),
  };
}

/**
 * Kiểm cả form TRƯỚC khi gửi, bằng đúng luật của `patchSchema` phía server.
 * Trả chuỗi rỗng nghĩa là hợp lệ.
 *
 * Có hàm này vì server gộp mọi lỗi zod thành đúng một câu "Dữ liệu không hợp
 * lệ" và client vứt mảng `issues` - nên không nói được là ô nào sai.
 */
export function kiemForm(form: AgentDetailForm): string {
  const loiSoBuoc = kiemSoBuoc(form.maxSteps);
  if (loiSoBuoc) return `Số bước tối đa: ${loiSoBuoc.toLowerCase()}`;
  if (form.icon.trim() === "") return "Icon không được để trống";
  if (form.name.trim() === "") return "Tên hiển thị không được để trống";
  const loiTran = kiemTranContext(form.contextWindow);
  if (loiTran) return `Trần context: ${loiTran.toLowerCase()}`;
  return "";
}
