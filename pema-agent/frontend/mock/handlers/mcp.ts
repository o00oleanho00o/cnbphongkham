// Mock of the MCP servers: default-deny per agent, and a server whose tool set changed waits for a person to
// approve it again (`can_duyet_lai`). Header values are never returned (`has_headers` only).
import { agents } from "./agents";
import {
  bodyOf,
  fail,
  isoFromNow,
  uid,
  DAY,
  HOUR,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const servers: S["McpServerView"][] = [
  {
    id: "mcp-lich-hen",
    name: "Lịch hẹn nội bộ",
    url: "https://mcp.pema.test/lich-hen",
    enabled: true,
    status: "da_ket_noi",
    error: "",
    has_headers: true,
    bound_agent_count: 1,
    tools_snapshot: [
      { name: "tim_lich_trong", description: "Tìm khung giờ còn trống của bác sĩ" },
      { name: "xem_lich_benh_nhan", description: "Xem lịch hẹn sắp tới (đã ẩn thông tin cá nhân)" },
    ],
    created_at: isoFromNow(-20 * DAY),
    updated_at: isoFromNow(-1 * HOUR),
  },
  {
    id: "mcp-tra-cuu-thuoc",
    name: "Tra cứu danh mục (bản thử)",
    url: "https://mcp.example.test/catalog",
    enabled: true,
    status: "can_duyet_lai",
    error: "",
    has_headers: false,
    bound_agent_count: 0,
    tools_snapshot: [{ name: "tim_san_pham", description: "Tìm sản phẩm trong danh mục" }],
    created_at: isoFromNow(-9 * DAY),
    updated_at: isoFromNow(-2 * HOUR),
  },
  {
    id: "mcp-loi",
    name: "Báo cáo ngoài",
    url: "https://mcp.broken.test/report",
    enabled: false,
    status: "loi",
    error: "Không kết nối được tới máy chủ MCP (hết thời gian chờ).",
    has_headers: true,
    bound_agent_count: 0,
    tools_snapshot: [],
    created_at: isoFromNow(-30 * DAY),
    updated_at: isoFromNow(-3 * DAY),
  },
];

const bindings = new Map<string, Set<string>>([["mcp-lich-hen", new Set(["tro-ly-noi-bo"])]]);

function serverOr404(id: string | undefined): S["McpServerView"] {
  const found = servers.find((s) => s.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy server MCP.");
  return found;
}

function withCount(server: S["McpServerView"]): S["McpServerView"] {
  return { ...server, bound_agent_count: bindings.get(server.id)?.size ?? 0 };
}

function agentsOfServer(id: string): string[] {
  return agents.filter((a) => bindings.get(id)?.has(a.id)).map((a) => a.id);
}

export function register(r: Router): void {
  r.get("/api/v1/admin/mcp/servers", "admin.mcp", (): Reply => ({ body: servers.map(withCount) }));

  r.post("/api/v1/admin/mcp/servers", "admin.mcp", (ctx): Reply => {
    const input = bodyOf<S["McpServerCreate"]>(ctx);
    if (!/^https?:\/\//.test(input.url))
      fail(422, "validation_failed", "URL phải bắt đầu bằng http:// hoặc https://");
    const created: S["McpServerView"] = {
      id: uid("mcp"),
      name: input.name,
      url: input.url,
      enabled: input.enabled ?? true,
      status: "cho_ket_noi",
      error: "",
      has_headers: Object.keys(input.headers ?? {}).length > 0,
      bound_agent_count: 0,
      tools_snapshot: [],
      created_at: isoFromNow(0),
      updated_at: isoFromNow(0),
    };
    servers.push(created);
    // The BE connects in the background: the badge turns to da_ket_noi on a later poll
    setTimeout(() => {
      created.status = "da_ket_noi";
      created.tools_snapshot = [{ name: "ping", description: "Kiểm tra kết nối" }];
      created.updated_at = isoFromNow(0);
    }, 3000);
    return { status: 201, body: created };
  });

  r.patch("/api/v1/admin/mcp/servers/{server_id}", "admin.mcp", (ctx): Reply => {
    const server = serverOr404(ctx.params.server_id);
    const input = bodyOf<S["McpServerUpdate"]>(ctx);
    if (input.name) server.name = input.name;
    if (input.url) server.url = input.url;
    if (input.enabled !== undefined && input.enabled !== null) server.enabled = input.enabled;
    if (input.headers)
      server.has_headers = Object.keys(input.headers).length > 0 || server.has_headers;
    server.updated_at = isoFromNow(0);
    return { body: withCount(server) };
  });

  r.delete("/api/v1/admin/mcp/servers/{server_id}", "admin.mcp", (ctx): Reply => {
    const server = serverOr404(ctx.params.server_id);
    servers.splice(servers.indexOf(server), 1);
    bindings.delete(server.id);
    return { status: 204 };
  });

  r.delete("/api/v1/admin/mcp/servers/{server_id}/headers", "admin.mcp", (ctx): Reply => {
    serverOr404(ctx.params.server_id).has_headers = false;
    return { status: 204 };
  });

  r.post("/api/v1/admin/mcp/servers/{server_id}/reapprove", "admin.mcp", (ctx): Reply => {
    const server = serverOr404(ctx.params.server_id);
    if (server.status !== "can_duyet_lai")
      fail(409, "invalid_state", "Server không ở trạng thái chờ duyệt lại.");
    server.status = "da_ket_noi";
    server.updated_at = isoFromNow(0);
    return { body: withCount(server) };
  });

  r.get("/api/v1/admin/mcp/servers/{server_id}/agents", "admin.mcp", (ctx): Reply => ({
    body: { ids: agentsOfServer(serverOr404(ctx.params.server_id).id) },
  }));

  r.put("/api/v1/admin/mcp/servers/{server_id}/agents", "admin.mcp", (ctx): Reply => {
    const server = serverOr404(ctx.params.server_id);
    const { ids } = bodyOf<S["IdList"]>(ctx);
    if (server.status === "can_duyet_lai" && ids.length > 0) {
      fail(409, "mcp_server_unapproved", "Server cần được duyệt lại trước khi gán cho agent.");
    }
    bindings.set(server.id, new Set(ids.filter((id) => agents.some((a) => a.id === id))));
    return { body: { ids: agentsOfServer(server.id) } };
  });

  r.get("/api/v1/admin/mcp/agents/{agent_id}/servers", "admin.mcp", (ctx): Reply => ({
    body: {
      ids: servers
        .filter((s) => bindings.get(s.id)?.has(ctx.params.agent_id ?? ""))
        .map((s) => s.id),
    },
  }));

  r.put("/api/v1/admin/mcp/agents/{agent_id}/servers", "admin.mcp", (ctx): Reply => {
    const agentId = ctx.params.agent_id ?? "";
    const { ids } = bodyOf<S["IdList"]>(ctx);
    servers.forEach((s) => {
      const set = bindings.get(s.id) ?? new Set<string>();
      if (ids.includes(s.id)) set.add(agentId);
      else set.delete(agentId);
      bindings.set(s.id, set);
    });
    return {
      body: { ids: servers.filter((s) => bindings.get(s.id)?.has(agentId)).map((s) => s.id) },
    };
  });
}
