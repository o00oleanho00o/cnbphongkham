// Mock of the tool catalog (per account and agent), the web search / fetch chains and the image generation
// settings. `blocked_by_policy` mirrors the patient_channel profile: image, video, document and web tools are
// off for an account on that profile whatever its toggles say.
import { accounts } from "./accounts";
import { agents } from "./agents";
import { vision } from "./model";
import { bodyOf, type Reply, type Router, type Schemas } from "../core";

type S = Schemas;

const BLOCKED_BY_PATIENT_CHANNEL = new Set([
  "send_file",
  "create_word_document",
  "create_excel_file",
  "create_image",
  "tai_video",
  "read_image",
  "web_search",
  "web_fetch",
]);

type Def = Pick<S["ToolOut"], "key" | "label" | "description" | "group" | "has_settings">;

const CATALOG: Def[] = [
  {
    key: "kb_search",
    label: "Tra cứu kho tri thức",
    description:
      "Tìm đoạn liên quan trong tài liệu phòng khám đã được duyệt rồi trả lời kèm nguồn.",
    group: "read",
    has_settings: false,
  },
  {
    key: "get_datetime",
    label: "Xem ngày giờ",
    description: "Biết hôm nay là ngày nào, giờ nào theo múi giờ phòng khám.",
    group: "read",
    has_settings: false,
  },
  {
    key: "web_search",
    label: "Tìm trên web",
    description: "Tra tin tức, thông tin công khai bên ngoài.",
    group: "read",
    has_settings: true,
  },
  {
    key: "web_fetch",
    label: "Đọc trang web",
    description: "Đọc nội dung một địa chỉ web (đã chặn địa chỉ nội bộ).",
    group: "read",
    has_settings: true,
  },
  {
    key: "read_image",
    label: "Nhìn kỹ ảnh",
    description: "Mô tả ảnh người dùng gửi thành chữ.",
    group: "read",
    has_settings: true,
  },
  {
    key: "get_group_info",
    label: "Thông tin nhóm",
    description: "Xem tên và thành viên của nhóm chat.",
    group: "read",
    has_settings: false,
  },
  {
    key: "save_memory",
    label: "Ghi nhớ",
    description: "Lưu một sự thật bền để lần sau còn nhớ.",
    group: "action",
    has_settings: false,
  },
  {
    key: "schedule_task",
    label: "Hẹn lịch",
    description: "Tạo việc chạy sau hoặc lặp lại.",
    group: "action",
    has_settings: false,
  },
  {
    key: "send_file",
    label: "Gửi tệp",
    description: "Gửi một tệp cho người đang chat.",
    group: "action",
    has_settings: false,
  },
  {
    key: "create_word_document",
    label: "Tạo tài liệu Word",
    description: "Soạn tệp .docx từ dữ liệu có cấu trúc.",
    group: "action",
    has_settings: false,
  },
  {
    key: "create_excel_file",
    label: "Tạo bảng Excel",
    description: "Soạn tệp .xlsx từ dữ liệu có cấu trúc.",
    group: "action",
    has_settings: false,
  },
  {
    key: "create_image",
    label: "Vẽ ảnh AI",
    description: "Vẽ mới hoặc sửa ảnh theo mô tả.",
    group: "action",
    has_settings: true,
  },
  {
    key: "tai_video",
    label: "Tải video",
    description: "Tải video từ liên kết công khai.",
    group: "action",
    has_settings: false,
  },
  {
    key: "tag_member",
    label: "Gắn thẻ thành viên",
    description: "Nhắc tên một thành viên trong nhóm.",
    group: "action",
    has_settings: false,
  },
];

const imageGen = { enabled: false, base_url: "", model: "", api_key: "" };

function imageOut(): S["ImageGenSettingsOut"] {
  return {
    enabled: imageGen.enabled,
    base_url: imageGen.base_url,
    model: imageGen.model,
    api_key_masked: imageGen.api_key ? `••••${imageGen.api_key.slice(-4)}` : "",
    has_override: Boolean(imageGen.base_url || imageGen.model),
  };
}

const searchChain: S["ToolChainSettings"] = {
  brave_api_key_set: false,
  fallback_enabled: null,
  steps: [
    { id: "brave", label: "Brave Search", enabled: false },
    { id: "duckduckgo", label: "DuckDuckGo", enabled: true },
  ],
};

const fetchChain: S["ToolChainSettings"] = {
  brave_api_key_set: false,
  fallback_enabled: false,
  steps: [
    { id: "direct", label: "Tự tải trực tiếp", enabled: true },
    { id: "jina", label: "Jina Reader", enabled: false },
  ],
};

function usable(key: string): { usable: boolean; hint: string | null } {
  if (key === "read_image" && !vision.enabled) {
    return { usable: false, hint: "Chưa cấu hình sidecar đọc ảnh (Settings)." };
  }
  if (key === "create_image" && !(imageGen.enabled && imageGen.base_url && imageGen.model)) {
    return { usable: false, hint: "Chưa cấu hình endpoint vẽ ảnh (Settings)." };
  }
  return { usable: true, hint: null };
}

function catalog(accountId: string | null, agentId: string | null): S["ToolOut"][] {
  const account = accounts.find((a) => a.id === accountId);
  const agent = agents.find((a) => a.id === (agentId ?? account?.agent_id));
  const patientChannel = (account?.policy_profile ?? agent?.policy_profile) === "patient_channel";
  return CATALOG.map((def) => ({
    ...def,
    ...usable(def.key),
    disabled_for_account: account?.disabled_tools?.includes(def.key) ?? false,
    disabled_for_agent: agent?.disabled_tools?.includes(def.key) ?? false,
    blocked_by_policy: patientChannel && BLOCKED_BY_PATIENT_CHANNEL.has(def.key),
  }));
}

function patchChain(
  chain: S["ToolChainSettings"],
  input: S["ToolChainUpdate"],
): S["ToolChainSettings"] {
  if (input.steps) chain.steps = input.steps;
  if (input.fallback_enabled !== undefined && input.fallback_enabled !== null) {
    chain.fallback_enabled = input.fallback_enabled;
  }
  if (input.brave_api_key !== undefined && input.brave_api_key !== null) {
    chain.brave_api_key_set = input.brave_api_key.length > 0;
  }
  return chain;
}

export function register(r: Router): void {
  r.get("/api/v1/admin/tools", "admin.tools", (ctx): Reply => ({
    body: catalog(ctx.query.get("account_id"), ctx.query.get("agent_id")),
  }));

  r.get("/api/v1/admin/tools/image-gen", "admin.tools", (): Reply => ({ body: imageOut() }));
  r.patch("/api/v1/admin/tools/image-gen", "admin.tools", (ctx): Reply => {
    const input = bodyOf<S["ImageGenSettingsUpdate"]>(ctx);
    if (input.enabled !== undefined && input.enabled !== null) imageGen.enabled = input.enabled;
    if (input.base_url !== undefined) imageGen.base_url = input.base_url ?? "";
    if (input.model !== undefined) imageGen.model = input.model ?? "";
    if (input.api_key) imageGen.api_key = input.api_key;
    return { body: imageOut() };
  });
  r.delete("/api/v1/admin/tools/image-gen", "admin.tools", (): Reply => {
    Object.assign(imageGen, { enabled: false, base_url: "", model: "", api_key: "" });
    return { status: 204 };
  });

  r.get("/api/v1/admin/tools/web_search", "admin.tools", (): Reply => ({ body: searchChain }));
  r.patch("/api/v1/admin/tools/web_search", "admin.tools", (ctx): Reply => ({
    body: patchChain(searchChain, bodyOf<S["ToolChainUpdate"]>(ctx)),
  }));
  r.get("/api/v1/admin/tools/web_fetch", "admin.tools", (): Reply => ({ body: fetchChain }));
  r.patch("/api/v1/admin/tools/web_fetch", "admin.tools", (ctx): Reply => ({
    body: patchChain(fetchChain, bodyOf<S["ToolChainUpdate"]>(ctx)),
  }));
}
