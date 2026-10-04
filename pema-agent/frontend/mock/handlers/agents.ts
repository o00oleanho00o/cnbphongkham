// Mock of the agents (persona, per-agent model overrides, disabled tools, policy profile).
// Fictional dermatology-clinic personas; the default profile of a new agent is the restrictive one.
import { accounts } from "./accounts";
import { CLINIC_ID } from "../auth";
import { bodyOf, fail, type Router, type Schemas } from "../core";

type S = Schemas;

const CSKH_PERSONA = `Bạn là trợ lý chăm sóc khách hàng của một phòng khám da liễu, xưng "em" và gọi khách là "chị" hoặc "anh".
Chỉ trả lời dựa trên tài liệu phòng khám đã được bác sĩ duyệt và luôn nêu nguồn.
Không chẩn đoán, không kê thuốc, không hứa kết quả điều trị.
Khi khách mô tả chảy máu, sốt, mưng mủ hoặc khó thở, dừng lại và báo nhân viên để bác sĩ liên hệ ngay.`;

export const agents: S["AgentOut"][] = [
  {
    id: "cskh-da-lieu",
    name: "CSKH Da liễu",
    icon: "🩺",
    persona: CSKH_PERSONA,
    clinic_id: CLINIC_ID,
    policy_profile: "patient_channel",
    is_default: true,
    model_provider: null,
    model_name: null,
    max_steps: null,
    reasoning_effort: null,
    context_window: null,
    disabled_tools: ["web_search", "web_fetch", "create_image"],
    account_count: 1,
  },
  {
    id: "tro-ly-noi-bo",
    name: "Trợ lý nội bộ",
    icon: "🗂️",
    persona:
      "Bạn hỗ trợ nhân viên phòng khám soạn nháp, tóm tắt hội thoại và tra cứu quy trình nội bộ. Không trả lời trực tiếp bệnh nhân.",
    clinic_id: CLINIC_ID,
    policy_profile: "staff_assistant",
    is_default: false,
    model_provider: null,
    model_name: null,
    max_steps: 6,
    reasoning_effort: "low",
    context_window: 128000,
    disabled_tools: [],
    account_count: 1,
  },
  {
    id: "bao-cao-tuan",
    name: "Báo cáo tuần",
    icon: "📊",
    persona: "",
    clinic_id: CLINIC_ID,
    policy_profile: "patient_channel",
    is_default: false,
    model_provider: "openai-compatible",
    model_name: "qwen3-8b",
    max_steps: 4,
    reasoning_effort: null,
    context_window: 32000,
    disabled_tools: [],
    account_count: 0,
  },
];

function definedOnly<T extends object>(patch: T): Partial<T> {
  return Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined)) as Partial<T>;
}

function agentOr404(id: string | undefined): S["AgentOut"] {
  const found = agents.find((a) => a.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy agent.");
  return found;
}

function withCounts(): S["AgentOut"][] {
  return agents.map((a) => ({
    ...a,
    account_count: accounts.filter((x) => x.agent_id === a.id).length,
  }));
}

export function register(r: Router): void {
  r.get("/api/v1/admin/agents", "admin.agents", () => ({ body: withCounts() }));

  r.post("/api/v1/admin/agents", "admin.agents", (ctx) => {
    const input = bodyOf<S["AgentCreate"]>(ctx);
    if (agents.some((a) => a.id === input.id)) {
      fail(409, "duplicate_request", "ID này đã có agent khác dùng.");
    }
    const created: S["AgentOut"] = {
      id: input.id,
      name: input.name,
      icon: input.icon ?? "🤖",
      persona: input.persona ?? "",
      clinic_id: CLINIC_ID,
      // The restrictive profile is the default of every new agent (fail safe).
      policy_profile: input.policy_profile ?? "patient_channel",
      is_default: false,
      model_provider: null,
      model_name: null,
      max_steps: null,
      reasoning_effort: null,
      context_window: null,
      disabled_tools: [],
      account_count: 0,
    };
    agents.push(created);
    return { status: 201, body: created };
  });

  r.patch("/api/v1/admin/agents/{agent_id}", "admin.agents", (ctx) => {
    const agent = agentOr404(ctx.params.agent_id);
    const { clear_model_override, ...patch } = bodyOf<S["AgentUpdate"]>(ctx);
    Object.assign(agent, definedOnly(patch));
    if (clear_model_override) {
      agent.model_provider = null;
      agent.model_name = null;
    }
    return { body: agent };
  });

  r.delete("/api/v1/admin/agents/{agent_id}", "admin.agents", (ctx) => {
    const agent = agentOr404(ctx.params.agent_id);
    if (agent.is_default) fail(409, "invalid_state", "Không xóa được agent mặc định.");
    if (accounts.some((a) => a.agent_id === agent.id)) {
      fail(
        409,
        "invalid_state",
        "Còn tài khoản đang dùng agent này. Gắn tài khoản sang agent khác trước.",
      );
    }
    agents.splice(agents.indexOf(agent), 1);
    return { status: 204 };
  });
}
