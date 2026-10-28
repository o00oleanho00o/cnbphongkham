// Fake Zalo connector for `bun run dev:mock` (docs/CONNECTOR-PROTOCOL.md section 5): `scripts/dev-mock.mjs` sets
// `PEMA_CONNECTOR_URLS=zalo=<this server>/connectors/zalo`, so the clinic web's `/connectors/zalo/...` proxy lands
// here (with the same short token as the agent; `answerAgent` in `agent.ts` checks it and strips `ZALO_BASE`). It
// answers the connector's admin UI listing, its built script and the lists the Zalo pages read, with FICTIONAL
// accounts and contacts. Not part of the clinic contract (`openapi.json`).
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { DAY, HOUR, MIN, Router, isoFromNow, type Ctx, type Reply } from "./core";

export const ZALO_BASE = "/connectors/zalo";

/** Where the connector's browser script is built. */
const SCRIPT_CANDIDATES = ["../../connectors/zalo/ui/dist/client.js"].map((path) =>
  fileURLToPath(new URL(path, import.meta.url)),
);

const ACCOUNT_DEFAULTS = {
  group_require_mention: true,
  respond_to_groups: false,
  group_allowlist: { mode: "all", group_ids: [] as string[] },
  listen_group_ids: [] as string[],
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
  { user_id: "u-mau-2001", display_name: "Bạn chưa nhắn (mẫu)", avatar_url: null },
  // enough friends to scroll the account form's list of people
  ...Array.from({ length: 12 }, (_, i) => ({
    user_id: `u-mau-21${String(i).padStart(2, "0")}`,
    display_name: `Bạn mẫu ${i + 1}`,
    avatar_url: null,
  })),
];

const groups = [
  { account_id: "zalo-cskh-mau", thread_id: "g-mau-01", name: "Nhóm hỏi đáp (mẫu)" },
  ...Array.from({ length: 8 }, (_, i) => ({
    account_id: "zalo-cskh-mau",
    thread_id: `g-mau-${String(i + 2).padStart(2, "0")}`,
    name: `Nhóm mẫu ${i + 2}`,
  })),
];

function numberOr(raw: string | null, fallback: number): number {
  const n = raw === null ? Number.NaN : Number.parseInt(raw, 10);
  return Number.isNaN(n) || n < 0 ? fallback : n;
}

function personal(ctx: Ctx): Reply | null {
  const account = accounts.find((a) => a.id === ctx.params.account_id);
  if (account?.channel === "zalo_personal") return null;
  return { status: 404, body: { detail: "Không có nick cá nhân này." } };
}

/** The routes of the connector, paths as the connector sees them (the proxy and `answerAgent` strip `ZALO_BASE`). */
export function buildZaloConnectorRouter(): Router {
  const r = new Router();
  r.get("/v1/admin/ui", null, (): Reply => ({
    body: { name: "zalo", script: "/ui/client.js", styles: [] },
  }));
  r.get("/ui/client.js", null, (): Reply => {
    const file = SCRIPT_CANDIDATES.find((path) => existsSync(path));
    if (!file) {
      return {
        status: 404,
        body: { detail: "the browser files are not built (bun run build in the connector's ui folder)" },
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
  // The mock ignores the account: the chat channel `zalo-cskh-mau` and the account `zalo-cskh-mau` differ by a prefix.
  r.get("/v1/plugins/zalo/contacts/names", null, (ctx): Reply => {
    const wanted = new Set((ctx.query.get("ids") ?? "").split(","));
    const names = contacts
      .filter((c) => wanted.has(c.user_id))
      .map((c) => [c.user_id, c.display_name]);
    return { body: Object.fromEntries(names) };
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
      bundled: true,
      installing: false,
      version: "0.1.0",
      running: true,
      error: null,
      log: [],
    },
  }));
  return r;
}
