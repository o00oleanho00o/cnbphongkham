// Fake agent service for `bun run dev:mock` (plan C): `scripts/dev-mock.mjs` points `PEMA_AGENT_INTERNAL_URL` at this
// server, so the clinic web's `/agent/...` proxy reaches it with a token from `POST /api/v1/auth/agent-token`. It
// answers only what the plugin pages read when they open: the list of plugin scripts and the agent's own admin
// routes. Zalo is a connector now: `PEMA_CONNECTOR_URLS` points `zalo` at `<this server>/connectors/zalo`, answered
// by `connector-zalo.ts` with the same token check. Not part of the clinic contract (`openapi.json`), so its routes
// live in their own table, not in `handlers/`.
import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";

import { registerAgentCases } from "./agent-cases";
import { registerAgentSettings } from "./agent-settings";
import { ZALO_BASE } from "./connector-zalo";
import { registerKnowledge } from "./knowledge";
import {
  DAY,
  HOUR,
  MIN,
  Router,
  bodyOf,
  isoFromNow,
  parseJson,
  readBody,
  type Ctx,
  type Reply,
} from "./core";

const PLUGINS_DIR = fileURLToPath(new URL("../../backend/apps/agent/plugins/", import.meta.url));
/** Plugins with a browser script, as `GET /v1/admin/ui` lists them. */
const UI_PLUGINS = ["knowledge"] as const;
const TOKEN_TTL_MS = 2 * MIN;
const AGENT_PATHS = ["/v1/", "/ui/", `${ZALO_BASE}/`];

const tokens = new Map<string, number>();

export function isAgentPath(pathname: string): boolean {
  return AGENT_PATHS.some((prefix) => pathname.startsWith(prefix));
}

/** A short agent token, like the clinic API's (`POST /auth/agent-token`). */
export function issueAgentToken(): { token: string; expires_at: string } {
  const token = `mock-agent-${randomUUID()}`;
  tokens.set(token, Date.now() + TOKEN_TTL_MS);
  return { token, expires_at: isoFromNow(TOKEN_TTL_MS) };
}

function tokenValid(authorization: string | undefined): boolean {
  const token = authorization?.startsWith("Bearer ") ? authorization.slice(7) : "";
  const expiresAt = tokens.get(token);
  return expiresAt !== undefined && expiresAt > Date.now();
}

/** The gateway's error shape: `{error: {kind, message}}`; plugin routes say `{detail}`. */
function gatewayError(status: number, kind: string, message: string): Reply {
  return { status, body: { error: { kind, message } } };
}

function numberOr(raw: string | null, fallback: number): number {
  const n = raw === null ? Number.NaN : Number.parseInt(raw, 10);
  return Number.isNaN(n) || n < 0 ? fallback : n;
}

type ModelShown = {
  provider: string;
  model: string;
  base_url: string | null;
  reasoning: string | null;
  dialect: string | null;
  window_tokens: number | null;
  api_key: string;
  api_key_broken: boolean;
  sources: Record<string, "db" | "profile" | "unset">;
  stored: boolean;
  entry_id: string | null;
};

const MODEL_FROM_PROFILE: ModelShown = {
  provider: "openai-compatible",
  model: "deepseek-chat",
  base_url: "https://api.deepseek.com/v1",
  reasoning: null,
  dialect: "deepseek",
  window_tokens: 128000,
  api_key: "",
  api_key_broken: false,
  sources: {
    provider: "profile",
    model: "profile",
    base_url: "profile",
    reasoning: "profile",
    dialect: "profile",
    window_tokens: "profile",
    api_key: "unset",
  },
  stored: false,
  entry_id: null,
};

let model: ModelShown = structuredClone(MODEL_FROM_PROFILE);

function patchModel(changes: Record<string, string | null>): ModelShown {
  const next = structuredClone(model);
  Object.entries(changes).forEach(([key, value]) => {
    if (key === "api_key") {
      next.api_key = value === null ? "" : "sk-…mẫu";
      next.sources.api_key = value === null ? "unset" : "db";
      return;
    }
    Object.assign(next, { [key]: value });
    next.sources[key] = "db";
  });
  next.stored = true;
  next.entry_id = null;
  model = next;
  return model;
}

type EntryFields = {
  label: string;
  provider: string;
  model: string;
  base_url: string | null;
  reasoning: string | null;
  dialect: string | null;
  window_tokens: number | null;
};
type EntryRow = EntryFields & { id: string; has_key: boolean };

const sampleEntry = (id: string, fields: EntryFields, hasKey = true): EntryRow => ({
  id: id.repeat(32).slice(0, 32),
  has_key: hasKey,
  ...fields,
});

let entries: EntryRow[] = [
  sampleEntry("a", {
    label: "DeepSeek công ty",
    provider: "openai-compatible",
    model: "deepseek-v4-pro",
    base_url: "https://api.deepseek.com",
    reasoning: null,
    dialect: "deepseek",
    window_tokens: 128000,
  }),
  sampleEntry("b", {
    label: "DeepSeek dự phòng",
    provider: "openai-compatible",
    model: "deepseek-v4-flash",
    base_url: "https://api.deepseek.com",
    reasoning: null,
    dialect: "deepseek",
    window_tokens: null,
  }),
  sampleEntry("c", {
    label: "OpenAI chăm sóc khách",
    provider: "openai-compatible",
    model: "gpt-5-mini",
    base_url: "https://api.openai.com/v1",
    reasoning: null,
    dialect: "openai",
    window_tokens: 400000,
  }),
  sampleEntry(
    "d",
    {
      label: "Claude thử",
      provider: "anthropic",
      model: "claude-sonnet-5-5",
      base_url: null,
      reasoning: null,
      dialect: null,
      window_tokens: 200000,
    },
    false,
  ),
];

const entryShown = (entry: EntryRow) => ({
  ...entry,
  api_key: entry.has_key ? "sk-…mẫu" : "",
  api_key_broken: false,
  active: model.entry_id === entry.id,
});

function changeEntry(ctx: Ctx): Reply {
  const found = entries.find((e) => e.id === ctx.params.entry_id);
  if (!found) return gatewayError(404, "not_found", "no such model in the list");
  const { api_key: key, ...fields } = bodyOf<Record<string, string | null>>(ctx);
  // A key not sent or sent empty is kept, null removes it, a value replaces it.
  const hasKey = key === undefined || key === "" ? found.has_key : key !== null;
  const next: EntryRow = { ...found, ...fields, has_key: hasKey };
  entries = entries.map((e) => (e.id === next.id ? next : e));
  if (model.entry_id === next.id) applyEntry(next);
  return { body: entryShown(next) };
}

function applyEntry(entry: EntryRow): void {
  model = {
    ...model,
    provider: entry.provider,
    model: entry.model,
    base_url: entry.base_url,
    reasoning: entry.reasoning,
    dialect: entry.dialect,
    window_tokens: entry.window_tokens ?? MODEL_FROM_PROFILE.window_tokens,
    api_key: entry.has_key ? "sk-…mẫu" : "",
    sources: { ...model.sources, api_key: entry.has_key ? "db" : "unset" },
    stored: true,
    entry_id: entry.id,
  };
}

type PluginShown = {
  name: string;
  version: string;
  description: string;
  origin: string;
  enabled: boolean;
  error: string | null;
  tools: string[];
  channels: string[];
  jobs: string[];
  settings: {
    key: string;
    type: "string" | "number" | "integer" | "boolean";
    title: string;
    description: string;
    required: boolean;
    sensitive: boolean;
    default: unknown;
    value: unknown;
    source: "admin" | "profile" | "default" | null;
  }[];
  secrets_unreadable: boolean;
};

const pluginList: PluginShown[] = [
  {
    name: "web",
    version: "0.1.0",
    description: "Bảng điều khiển và đăng nhập của dịch vụ agent.",
    origin: "bundled",
    enabled: true,
    error: null,
    tools: [],
    channels: [],
    jobs: [],
    settings: [],
    secrets_unreadable: false,
  },
  {
    name: "sso",
    version: "0.1.0",
    description: "Tin các token do một nơi cấp (clinic API) đã ký.",
    origin: "bundled",
    enabled: true,
    error: null,
    tools: [],
    channels: [],
    jobs: [],
    settings: [
      {
        key: "issuer",
        type: "string",
        title: "Issuer",
        description: "Tên nơi cấp token",
        required: true,
        sensitive: false,
        default: null,
        value: "pema-clinic",
        source: "profile",
      },
      {
        key: "jwks_url",
        type: "string",
        title: "Địa chỉ khóa công khai",
        description: "",
        required: true,
        sensitive: false,
        default: null,
        value: "http://api:8000/api/v1/.well-known/jwks.json",
        source: "profile",
      },
    ],
    secrets_unreadable: false,
  },
  {
    name: "knowledge",
    version: "0.1.0",
    description:
      "Kho tri thức: các tài liệu agent tra cứu. Thêm, duyệt nguồn, dạy tên dịch vụ, thử tìm.",
    origin: "bundled",
    enabled: true,
    error: null,
    tools: [],
    channels: [],
    jobs: [],
    settings: [],
    secrets_unreadable: false,
  },
];

function pluginNamed(ctx: Ctx): PluginShown | undefined {
  return pluginList.find((p) => p.name === ctx.params.name);
}

/** `PATCH .../settings`: the values given replace the stored ones (`null` goes back to the default). */
function saveSettings(ctx: Ctx): Reply {
  const plugin = pluginNamed(ctx);
  if (!plugin) return { status: 404, body: { detail: "Không có plugin này." } };
  const given = bodyOf<{ settings?: Record<string, unknown> }>(ctx).settings ?? {};
  plugin.settings = plugin.settings.map((setting) =>
    setting.key in given
      ? {
          ...setting,
          value: given[setting.key] ?? setting.default,
          source: given[setting.key] === null ? "default" : "admin",
        }
      : setting,
  );
  return { body: plugin };
}

function switchPlugin(ctx: Ctx, enabled: boolean): Reply {
  const plugin = pluginNamed(ctx);
  if (!plugin) return { status: 404, body: { detail: "Không có plugin này." } };
  plugin.enabled = enabled;
  return { body: plugin };
}

// Fictional activity of the agent: two chats on the Zalo channel and one over HTTP, their turns and a fortnight of usage.
type MockMessage = { role: string; text: string; tools: string[]; at: string };
type MockSession = {
  session_id: string;
  channel: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  summary: string | null;
  messages: MockMessage[];
};

let sessions: MockSession[] = [
  {
    session_id: "clinic:zalo-cskh-mau:u-mau-1001:0",
    channel: "zalo-cskh-mau",
    user_id: "u-mau-1001",
    created_at: isoFromNow(-3 * HOUR),
    updated_at: isoFromNow(-20 * MIN),
    summary: null,
    messages: [
      {
        role: "user",
        text: "Cho mình hỏi giá laser trị nám?",
        tools: [],
        at: isoFromNow(-3 * HOUR),
      },
      {
        role: "assistant",
        text: "Dạ, bên em có gói laser trị nám từ 1.500.000đ/lần. Chị muốn em đặt lịch tư vấn không ạ?",
        tools: ["kb_search"],
        at: isoFromNow(-3 * HOUR + MIN),
      },
    ],
  },
  {
    session_id: "clinic:zalo-cskh-mau:u-mau-1002:0",
    channel: "zalo-cskh-mau",
    user_id: "u-mau-1002",
    created_at: isoFromNow(-2 * DAY),
    updated_at: isoFromNow(-26 * HOUR),
    summary: "Khách hỏi về lịch tái khám sau tiêm filler; đã hẹn thứ Sáu.",
    messages: [
      {
        role: "user",
        text: "Mai mình tái khám được không?",
        tools: [],
        at: isoFromNow(-26 * HOUR),
      },
    ],
  },
  {
    session_id: "clinic:http:u-mau-03:0",
    channel: "http",
    user_id: "u-mau-03",
    created_at: isoFromNow(-5 * HOUR),
    updated_at: isoFromNow(-5 * HOUR),
    summary: null,
    messages: [],
  },
];

const TURN_IDS = [
  "00000000-0000-4000-8a00-000000000001",
  "00000000-0000-4000-8a00-000000000002",
  "00000000-0000-4000-8a00-000000000003",
];

const turns = [
  {
    turn_id: TURN_IDS[0],
    session_id: "clinic:zalo-cskh-mau:u-mau-1001:0",
    channel: "zalo-cskh-mau",
    user_id: "u-mau-1001",
    model: "deepseek-v4-pro",
    started_at: isoFromNow(-3 * HOUR),
    duration_ms: 4200,
    stop: "completed",
    steps: 2,
    error_kind: null as string | null,
    input_tokens: 1820,
    output_tokens: 96,
  },
  {
    turn_id: TURN_IDS[1],
    session_id: "clinic:zalo-cskh-mau:u-mau-1002:0",
    channel: "zalo-cskh-mau",
    user_id: "u-mau-1002",
    model: "deepseek-v4-pro",
    started_at: isoFromNow(-26 * HOUR),
    duration_ms: 1500,
    stop: "completed",
    steps: 1,
    error_kind: null as string | null,
    input_tokens: 940,
    output_tokens: 40,
  },
  {
    turn_id: TURN_IDS[2],
    session_id: "clinic:http:u-mau-03:0",
    channel: "http",
    user_id: "u-mau-03",
    model: "deepseek-v4-pro",
    started_at: isoFromNow(-5 * HOUR),
    duration_ms: 800,
    stop: "error",
    steps: 1,
    error_kind: "auth" as string | null,
    input_tokens: 0,
    output_tokens: 0,
  },
];

const turnEvents = [
  {
    kind: "model_call",
    step: 1,
    name: "",
    duration_ms: 2100,
    is_error: false,
    detail: { stop: "tool_use" },
  },
  {
    kind: "tool_call",
    step: 1,
    name: "kb_search",
    duration_ms: 350,
    is_error: false,
    detail: { size: 812 },
  },
  {
    kind: "model_call",
    step: 2,
    name: "",
    duration_ms: 1700,
    is_error: false,
    detail: { stop: "end" },
  },
];

const PAGE = 30;

function pageOf<T>(items: T[], ctx: Ctx): { items: T[]; has_more: boolean } {
  const start = numberOr(ctx.query.get("page"), 0) * PAGE;
  return { items: items.slice(start, start + PAGE), has_more: items.length > start + PAGE };
}

function sessionRow(session: MockSession) {
  const { messages, summary, ...row } = session;
  return { ...row, message_count: messages.length, compacted: summary !== null };
}

function usageDays(days: number) {
  return Array.from({ length: days }, (_, index) => {
    const back = days - 1 - index;
    const turnsThatDay = back === 0 ? 2 : (index * 5) % 9;
    return {
      day: new Date(Date.now() - back * DAY).toISOString().slice(0, 10),
      turns: turnsThatDay,
      failed: back === 0 ? 1 : 0,
      input_tokens: turnsThatDay * 900,
      output_tokens: turnsThatDay * 60,
    };
  });
}

export function buildAgentRouter(): Router {
  const r = new Router();
  r.get("/v1/admin/sessions", null, (ctx): Reply => {
    const channel = ctx.query.get("channel") ?? "";
    const q = (ctx.query.get("q") ?? "").toLowerCase();
    const found = sessions
      .filter((s) => channel === "" || s.channel === channel)
      .filter((s) => q === "" || `${s.user_id} ${s.session_id}`.toLowerCase().includes(q))
      .map(sessionRow);
    return { body: pageOf(found, ctx) };
  });
  r.get("/v1/admin/sessions/{session_id}", null, (ctx): Reply => {
    const found = sessions.find((s) => s.session_id === ctx.params.session_id);
    if (!found) return gatewayError(404, "not_found", "no such session");
    return { body: { ...sessionRow(found), summary: found.summary, messages: found.messages } };
  });
  r.delete("/v1/admin/sessions/{session_id}", null, (ctx): Reply => {
    if (!sessions.some((s) => s.session_id === ctx.params.session_id)) {
      return gatewayError(404, "not_found", "no such session");
    }
    sessions = sessions.filter((s) => s.session_id !== ctx.params.session_id);
    return { body: { deleted: ctx.params.session_id } };
  });
  r.post("/v1/admin/sessions/delete", null, (ctx): Reply => {
    const ids = bodyOf<{ session_ids?: string[] }>(ctx).session_ids ?? [];
    if (ids.length === 0 || ids.length > 100) {
      return gatewayError(422, "invalid_request", "session_ids must hold 1 to 100 ids");
    }
    const before = sessions.length;
    sessions = sessions.filter((s) => !ids.includes(s.session_id));
    return { body: { deleted: before - sessions.length } };
  });
  r.get("/v1/admin/traces", null, (ctx): Reply => {
    const channel = ctx.query.get("channel") ?? "";
    const session = ctx.query.get("session_id") ?? "";
    const errorsOnly = ctx.query.get("errors_only") === "true";
    const found = turns
      .filter((t) => channel === "" || t.channel === channel)
      .filter((t) => session === "" || t.session_id === session)
      .filter((t) => !errorsOnly || t.stop !== "completed");
    return { body: pageOf(found, ctx) };
  });
  r.get("/v1/admin/traces/{turn_id}", null, (ctx): Reply => {
    const found = turns.find((t) => t.turn_id === ctx.params.turn_id);
    if (!found) return gatewayError(404, "not_found", "no such turn");
    return {
      body: {
        ...found,
        compactions: 0,
        cache_read_tokens: 640,
        cache_write_tokens: 0,
        reasoning_tokens: 0,
        events: found.stop === "completed" ? turnEvents : [],
      },
    };
  });
  r.get("/v1/admin/usage", null, (ctx): Reply => {
    const days = Math.max(1, Math.min(numberOr(ctx.query.get("days"), 14), 90));
    return { body: { today: new Date().toISOString().slice(0, 10), days: usageDays(days) } };
  });
  r.get("/v1/admin/channels", null, (): Reply => ({
    body: { channels: [{ name: "zalo-cskh-mau", running: true, error: null }] },
  }));
  r.get("/v1/admin/jobs", null, (): Reply => ({
    body: {
      jobs: [
        { name: "zalo:accounts", running: true, error: null },
        { name: "zalo:bridge", running: true, error: null },
        { name: "zalo:friend_auto_accept", running: false, error: "Bridge chưa sẵn sàng" },
      ],
    },
  }));
  r.get("/v1/admin/model", null, (): Reply => ({ body: model }));
  r.patch("/v1/admin/model", null, (ctx): Reply => ({
    body: patchModel(bodyOf<Record<string, string | null>>(ctx)),
  }));
  r.delete("/v1/admin/model", null, (): Reply => {
    model = structuredClone(MODEL_FROM_PROFILE);
    return { body: model };
  });
  r.get("/v1/admin/model/entries", null, (): Reply => ({
    body: { entries: entries.map(entryShown) },
  }));
  r.post("/v1/admin/model/entries", null, (ctx): Reply => {
    const body = bodyOf<Partial<EntryFields> & { api_key?: string }>(ctx);
    const row: EntryRow = {
      id: randomUUID().replaceAll("-", ""),
      label: body.label ?? "",
      provider: body.provider ?? "openai-compatible",
      model: body.model ?? "",
      base_url: body.base_url ?? null,
      reasoning: body.reasoning ?? null,
      dialect: body.dialect ?? null,
      window_tokens: body.window_tokens ?? null,
      has_key: Boolean(body.api_key),
    };
    entries = [...entries, row];
    return { status: 201, body: entryShown(row) };
  });
  r.patch("/v1/admin/model/entries/{entry_id}", null, (ctx): Reply => changeEntry(ctx));
  r.delete("/v1/admin/model/entries/{entry_id}", null, (ctx): Reply => {
    const found = entries.find((e) => e.id === ctx.params.entry_id);
    if (!found) return gatewayError(404, "not_found", "no such model in the list");
    entries = entries.filter((e) => e !== found);
    if (model.entry_id === found.id) model = { ...model, entry_id: null };
    return { body: { deleted: found.id } };
  });
  r.post("/v1/admin/model/entries/{entry_id}/use", null, (ctx): Reply => {
    const found = entries.find((e) => e.id === ctx.params.entry_id);
    if (!found) return gatewayError(404, "not_found", "no such model in the list");
    applyEntry(found);
    return { body: model };
  });
  r.post("/v1/admin/model/entries/{entry_id}/test", null, (ctx): Reply => {
    const found = entries.find((e) => e.id === ctx.params.entry_id);
    if (!found) return gatewayError(404, "not_found", "no such model in the list");
    return found.has_key
      ? { body: { ok: true, model: found.model, latency_ms: 380 } }
      : { status: 502, body: { ok: false, model: found.model, error_kind: "config" } };
  });
  r.post("/v1/admin/model/list", null, (): Reply => ({
    body: { ok: true, models: ["deepseek-v4-flash", "deepseek-v4-pro"] },
  }));
  r.post("/v1/admin/model/test", null, (): Reply => ({
    body: { ok: true, model: model.model, latency_ms: 420 },
  }));
  r.get("/v1/admin/plugins", null, (): Reply => ({ body: { plugins: pluginList, broken: {} } }));
  r.post("/v1/admin/plugins/{name}/enable", null, (ctx): Reply => switchPlugin(ctx, true));
  r.post("/v1/admin/plugins/{name}/disable", null, (ctx): Reply => switchPlugin(ctx, false));
  r.patch("/v1/admin/plugins/{name}/settings", null, (ctx): Reply => saveSettings(ctx));
  r.get("/v1/admin/ui", null, (): Reply => ({
    body: {
      home: "/ui/web/index.html",
      plugins: UI_PLUGINS.map((name) => ({
        name,
        script: `/ui/${name}/client.js`,
        styles: [],
      })),
    },
  }));
  r.get("/ui/{plugin}/client.js", null, (ctx): Reply => {
    const plugin = UI_PLUGINS.find((name) => name === ctx.params.plugin);
    const file = plugin && `${PLUGINS_DIR}${plugin}/ui/dist/client.js`;
    if (!file || !existsSync(file)) {
      return {
        status: 404,
        body: {
          detail: "the browser files are not built (bun run build in the plugin's ui folder)",
        },
      };
    }
    return {
      raw: readFileSync(file),
      headers: { "content-type": "text/javascript; charset=utf-8", "cache-control": "no-cache" },
    };
  });
  registerAgentSettings(r);
  registerAgentCases(r);
  registerKnowledge(r);
  return r;
}

/** One request to the fake agent, or to the fake Zalo connector (`/connectors/zalo/...`): the bearer token first. */
export async function answerAgent(
  routers: { agent: Router; zalo: Router },
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
): Promise<Reply> {
  if (!tokenValid(req.headers.authorization)) {
    return gatewayError(401, "unauthorized", "Thiếu hoặc sai mã truy cập agent.");
  }
  const toZalo = url.pathname.startsWith(`${ZALO_BASE}/`);
  const router = toZalo ? routers.zalo : routers.agent;
  const path = toZalo ? url.pathname.slice(ZALO_BASE.length) : url.pathname;
  const found = router.match(req.method ?? "GET", path);
  if (!found) return gatewayError(404, "not_found", "Không có đường dẫn này ở agent.");
  const raw = await readBody(req);
  const isJson = (req.headers["content-type"] ?? "").includes("application/json");
  return found.route.handler({
    req,
    res,
    params: found.params,
    query: url.searchParams,
    session: null,
    body: isJson ? parseJson(raw) : {},
    raw,
  });
}
