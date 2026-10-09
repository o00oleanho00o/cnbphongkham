// Fake agent service for `pnpm dev:mock` (plan C): `scripts/dev-mock.mjs` points `PEMA_AGENT_INTERNAL_URL` at this
// server, so the clinic web's `/agent/...` proxy reaches it with a token from `POST /api/v1/auth/agent-token`. It
// answers only what the plugin pages read when they open: the list of plugin scripts, the Zalo plugin's built
// script and the Zalo plugin's lists, with FICTIONAL accounts and contacts. Not part of the clinic contract
// (`openapi.json`), so its routes live in their own table, not in `handlers/`.
import { randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import type { IncomingMessage, ServerResponse } from "node:http";
import { fileURLToPath } from "node:url";

import { DAY, HOUR, MIN, Router, isoFromNow, type Ctx, type Reply } from "./core";

const PLUGINS_DIR = fileURLToPath(new URL("../../backend/apps/agent/plugins/", import.meta.url));
/** Plugins with a browser script, as `GET /v1/admin/ui` lists them. */
const UI_PLUGINS = ["zalo"] as const;
const TOKEN_TTL_MS = 2 * MIN;
const AGENT_PATHS = ["/v1/", "/ui/"];

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

const ACCOUNT_DEFAULTS = {
  group_require_mention: true,
  respond_to_groups: false,
  group_passive_listen: false,
  auto_react_icon: "heart",
  typing_indicator_enabled: true,
  disabled_tools: [] as string[],
  auto_accept_friend_delay_minutes: 5,
  warning: null,
};

const accounts = [
  {
    ...ACCOUNT_DEFAULTS,
    id: "zalo-cskh-mau",
    label: "Zalo CSKH (mẫu)",
    channel: "zalo_personal",
    enabled: true,
    allowlist: { mode: "list", user_ids: ["u-mau-1001"] },
    auto_react_enabled: true,
    auto_accept_friends: false,
    running: true,
    has_credentials: true,
  },
  {
    ...ACCOUNT_DEFAULTS,
    id: "bot-dat-lich-mau",
    label: "Bot đặt lịch (mẫu)",
    channel: "zalo_bot",
    enabled: false,
    allowlist: { mode: "all", user_ids: [] as string[] },
    auto_react_enabled: false,
    auto_accept_friends: false,
    running: false,
    has_credentials: false,
  },
];

const contacts = [
  {
    account_id: "zalo-cskh-mau",
    user_id: "u-mau-1001",
    display_name: "Khách mẫu Một",
    first_seen: isoFromNow(-20 * DAY),
    last_seen: isoFromNow(-2 * HOUR),
    message_count: 14,
  },
  {
    account_id: "zalo-cskh-mau",
    user_id: "u-mau-1002",
    display_name: "Khách mẫu Hai",
    first_seen: isoFromNow(-3 * DAY),
    last_seen: isoFromNow(-30 * MIN),
    message_count: 3,
  },
  {
    account_id: "bot-dat-lich-mau",
    user_id: "u-mau-2001",
    display_name: "Khách mẫu Ba",
    first_seen: isoFromNow(-9 * DAY),
    last_seen: isoFromNow(-1 * DAY),
    message_count: 6,
  },
];

const friendRequests = [
  {
    from_uid: "u-mau-3001",
    message: "Chào phòng khám, mình muốn hỏi lịch (mẫu)",
    sender_name: "Khách mẫu Bốn",
    avatar_url: null,
    received_at: isoFromNow(-45 * MIN),
  },
];

const friends = [
  { user_id: "u-mau-1001", display_name: "Khách mẫu Một", avatar_url: null },
  { user_id: "u-mau-1002", display_name: "Khách mẫu Hai", avatar_url: null },
];

const groups = [{ account_id: "zalo-cskh-mau", thread_id: "g-mau-01", name: "Nhóm hỏi đáp (mẫu)" }];

function numberOr(raw: string | null, fallback: number): number {
  const n = raw === null ? Number.NaN : Number.parseInt(raw, 10);
  return Number.isNaN(n) || n < 0 ? fallback : n;
}

function personal(ctx: Ctx): Reply | null {
  const account = accounts.find((a) => a.id === ctx.params.account_id);
  if (account?.channel === "zalo_personal") return null;
  return { status: 404, body: { detail: "Không có nick cá nhân này." } };
}

export function buildAgentRouter(): Router {
  const r = new Router();
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
        body: { detail: "the browser files are not built (pnpm build in the plugin's ui folder)" },
      };
    }
    return {
      raw: readFileSync(file),
      headers: { "content-type": "text/javascript; charset=utf-8", "cache-control": "no-cache" },
    };
  });
  r.get("/v1/plugins/zalo/accounts", null, (): Reply => ({ body: accounts }));
  r.get("/v1/plugins/zalo/contacts", null, (ctx): Reply => {
    const account = ctx.query.get("account_id");
    const q = (ctx.query.get("q") ?? "").toLowerCase();
    const offset = numberOr(ctx.query.get("offset"), 0);
    const limit = numberOr(ctx.query.get("limit"), 50);
    const found = contacts
      .filter((c) => !account || c.account_id === account)
      .filter((c) => !q || `${c.display_name} ${c.user_id}`.toLowerCase().includes(q));
    return { body: found.slice(offset, offset + limit) };
  });
  r.get("/v1/plugins/zalo/friends/{account_id}/requests", null, (ctx): Reply => {
    return personal(ctx) ?? { body: friendRequests };
  });
  r.get("/v1/plugins/zalo/friends/{account_id}/list", null, (ctx): Reply => {
    return personal(ctx) ?? { body: friends };
  });
  r.get("/v1/plugins/zalo/groups", null, (ctx): Reply => {
    const account = ctx.query.get("account_id");
    return { body: groups.filter((g) => !account || g.account_id === account) };
  });
  r.get("/v1/plugins/zalo/bridge", null, (): Reply => ({
    body: {
      installed: true,
      installing: false,
      version: "0.1.0",
      running: true,
      error: null,
      log: [],
    },
  }));
  return r;
}

/** One request to the fake agent: the bearer token first, like the gateway. */
export async function answerAgent(
  router: Router,
  req: IncomingMessage,
  res: ServerResponse,
  url: URL,
): Promise<Reply> {
  if (!tokenValid(req.headers.authorization)) {
    return gatewayError(401, "unauthorized", "Thiếu hoặc sai mã truy cập agent.");
  }
  const found = router.match(req.method ?? "GET", url.pathname);
  if (!found) return gatewayError(404, "not_found", "Không có đường dẫn này ở agent.");
  return found.route.handler({
    req,
    res,
    params: found.params,
    query: url.searchParams,
    session: null,
    body: {},
    raw: Buffer.alloc(0),
  });
}
