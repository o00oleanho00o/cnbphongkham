// Mock of Zalo accounts, QR login, friends, the channel switchboard (kill switch) and the policy profile
// assignment of an account. Fictional accounts; the bot token is never returned (`has_bot_token` only).
import { crc32, deflateSync } from "node:zlib";

import { CLINIC_ID } from "../auth";

import {
  bodyOf,
  fail,
  isoFromNow,
  HOUR,
  MIN,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

export const accounts: S["AccountOut"][] = [
  {
    id: "pema-bot",
    label: "Pema CSKH (Zalo Bot)",
    channel: "zalo_bot",
    clinic_id: CLINIC_ID,
    agent_id: "cskh-da-lieu",
    policy_profile: "patient_channel",
    enabled: true,
    running: true,
    has_bot_token: true,
    has_credentials: false,
    allowlist: { mode: "all", user_ids: [] },
    respond_to_groups: false,
    group_require_mention: true,
    group_passive_listen: false,
    auto_react_enabled: false,
    auto_react_icon: "like",
    typing_indicator_enabled: true,
    disabled_tools: [],
    auto_accept_friends: false,
    auto_accept_friend_delay_minutes: 0,
  },
  {
    id: "le-tan-ca-nhan",
    label: "Zalo lễ tân (cá nhân)",
    channel: "zalo_personal",
    clinic_id: CLINIC_ID,
    agent_id: "tro-ly-noi-bo",
    policy_profile: "staff_assistant",
    enabled: true,
    running: true,
    has_bot_token: false,
    has_credentials: true,
    allowlist: { mode: "list", user_ids: ["u-demo-021", "u-demo-022"] },
    respond_to_groups: true,
    group_require_mention: true,
    group_passive_listen: false,
    auto_react_enabled: true,
    auto_react_icon: "heart",
    typing_indicator_enabled: true,
    disabled_tools: ["web_search"],
    auto_accept_friends: true,
    auto_accept_friend_delay_minutes: 5,
  },
  {
    id: "noi-bo",
    label: "Pema Nội bộ",
    channel: "zalo_personal",
    clinic_id: CLINIC_ID,
    agent_id: "tro-ly-noi-bo",
    policy_profile: "staff_assistant",
    enabled: true,
    running: true,
    has_bot_token: false,
    has_credentials: true,
    allowlist: { mode: "list", user_ids: [] },
    respond_to_groups: false,
    group_require_mention: true,
    group_passive_listen: false,
    auto_react_enabled: false,
    auto_react_icon: "like",
    typing_indicator_enabled: false,
    disabled_tools: [],
    auto_accept_friends: false,
    auto_accept_friend_delay_minutes: 0,
  },
];

export const channels: S["ChannelSettingsOut"][] = [
  {
    channel: "zalo_bot",
    enabled: true,
    kill_switch_on: false,
    daily_cap: 10,
    min_gap_seconds: 20,
    max_gap_seconds: 90,
    send_window_start: "08:00",
    send_window_end: "20:00",
    proactive_sent_today: 3,
    requires_friend: false,
    bridge_state: null,
    updated_at: isoFromNow(-2 * HOUR),
    version: 1,
  },
  {
    channel: "zalo_personal",
    enabled: true,
    kill_switch_on: false,
    daily_cap: 5,
    min_gap_seconds: 60,
    max_gap_seconds: 240,
    send_window_start: "09:00",
    send_window_end: "18:00",
    proactive_sent_today: 0,
    requires_friend: true,
    bridge_state: "awaiting_qr",
    updated_at: isoFromNow(-5 * HOUR),
    version: 1,
  },
  {
    channel: "zalo_oa",
    enabled: false,
    kill_switch_on: false,
    daily_cap: null,
    min_gap_seconds: 0,
    max_gap_seconds: 0,
    send_window_start: null,
    send_window_end: null,
    proactive_sent_today: 0,
    requires_friend: false,
    bridge_state: "not_configured",
    updated_at: null,
    version: 1,
  },
];

const friends: S["FriendOut"][] = [
  { user_id: "u-demo-031", display_name: "Mai Linh (mẫu)", avatar_url: null },
  { user_id: "u-demo-032", display_name: "Thu Trang (mẫu)", avatar_url: null },
  { user_id: "u-demo-033", display_name: "Quốc Khánh (mẫu)", avatar_url: null },
];

let friendRequests: S["FriendRequestOut"][] = [
  {
    from_uid: "u-demo-041",
    sender_name: "Hải Yến (mẫu)",
    message: "Chào phòng khám, mình muốn hỏi lịch.",
    received_at: isoFromNow(-20 * MIN),
    avatar_url: null,
  },
  {
    from_uid: "u-demo-042",
    sender_name: null,
    message: "",
    received_at: isoFromNow(-3 * HOUR),
    avatar_url: null,
  },
];

const REACTIONS: S["ReactionIcon"][] = [
  { key: "like", emoji: "👍" },
  { key: "heart", emoji: "❤️" },
  { key: "haha", emoji: "😆" },
];

function accountOr404(id: string | undefined): S["AccountOut"] {
  const found = accounts.find((a) => a.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy tài khoản.");
  return found;
}

function channelOr404(name: string | undefined): S["ChannelSettingsOut"] {
  const found = channels.find((c) => c.channel === name);
  if (!found) fail(404, "not_found", "Không tìm thấy kênh.");
  return found;
}

/** Drop `null`/`undefined` so a PATCH only changes what was sent. */
function definedOnly<T extends object>(patch: T): Partial<T> {
  return Object.fromEntries(
    Object.entries(patch).filter(([, v]) => v !== undefined && v !== null),
  ) as Partial<T>;
}

// ----------------------------------------------------------------- fake QR

const QR_MODULES = 29;
const QR_SCALE = 6;

function pngChunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(body) >>> 0);
  return Buffer.concat([length, body, checksum]);
}

/** A QR-looking black and white picture (NOT a real code) so the modal has something to show. */
function fakeQrPng(): string {
  const size = QR_MODULES * QR_SCALE;
  const finder = (x: number, y: number) => {
    const inBox = (ox: number, oy: number) => x >= ox && x < ox + 7 && y >= oy && y < oy + 7;
    const ring = (ox: number, oy: number) =>
      inBox(ox, oy) &&
      !(
        x > ox &&
        x < ox + 6 &&
        y > oy &&
        y < oy + 6 &&
        !(x > ox + 1 && x < ox + 5 && y > oy + 1 && y < oy + 5)
      );
    return ring(0, 0) || ring(QR_MODULES - 7, 0) || ring(0, QR_MODULES - 7);
  };
  const dark = (mx: number, my: number) =>
    finder(mx, my) ||
    ((mx * 7 + my * 13 + mx * my) % 5 < 2 &&
      !(mx < 8 && my < 8) &&
      !(mx > QR_MODULES - 9 && my < 8) &&
      !(mx < 8 && my > QR_MODULES - 9));
  const rows = Array.from({ length: size }, (_, y) =>
    Buffer.from([
      0,
      ...Array.from({ length: size }, (_, x) =>
        dark(Math.floor(x / QR_SCALE), Math.floor(y / QR_SCALE)) ? 0 : 255,
      ),
    ]),
  );
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 0, 0, 0, 0], 8);
  const png = Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(Buffer.concat(rows))),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
  return png.toString("base64");
}

const qrSessions = new Map<string, { polls: number }>();

const QR_STEPS: S["QrLoginStatus"][] = [
  { state: "waiting_scan", qr_png_base64: null, detail: "Mở Zalo trên điện thoại và quét mã." },
  { state: "waiting_scan", qr_png_base64: null, detail: "Mở Zalo trên điện thoại và quét mã." },
  {
    state: "scanned",
    qr_png_base64: null,
    detail: "Đã quét, hãy xác nhận đăng nhập trên điện thoại.",
  },
  { state: "success", qr_png_base64: null, detail: "Đăng nhập thành công." },
];

function qrStatus(accountId: string): S["QrLoginStatus"] {
  const session = qrSessions.get(accountId);
  if (!session) return { state: "idle", qr_png_base64: null, detail: null };
  const step = QR_STEPS[Math.min(session.polls, QR_STEPS.length - 1)] ?? QR_STEPS[0];
  session.polls += 1;
  const result: S["QrLoginStatus"] = {
    ...(step as S["QrLoginStatus"]),
    qr_png_base64: step?.state === "waiting_scan" ? fakeQrPng() : null,
  };
  if (result.state === "success") {
    const account = accounts.find((a) => a.id === accountId);
    if (account) {
      account.has_credentials = true;
      account.running = true;
    }
    qrSessions.delete(accountId);
  }
  return result;
}

// ------------------------------------------------------------------ routes

export function register(r: Router): void {
  r.get("/api/v1/admin/accounts", "admin.accounts", (): Reply => ({ body: accounts }));

  r.post("/api/v1/admin/accounts", "admin.accounts", (ctx): Reply => {
    const input = bodyOf<S["AccountCreate"]>(ctx);
    if (accounts.some((a) => a.id === input.id)) {
      fail(409, "duplicate_request", "Mã tài khoản đã tồn tại.");
    }
    const created: S["AccountOut"] = {
      ...(accounts[0] as S["AccountOut"]),
      id: input.id,
      label: input.label,
      channel: input.channel ?? "zalo_bot",
      agent_id: input.agent_id ?? "cskh-da-lieu",
      // The restrictive profile is the default: a new account must never start permissive.
      policy_profile: input.policy_profile ?? "patient_channel",
      enabled: true,
      running: false,
      has_bot_token: false,
      has_credentials: false,
    };
    accounts.push(created);
    return { status: 201, body: created };
  });

  r.get("/api/v1/admin/accounts/reaction-icons", "admin.accounts", (): Reply => ({
    body: REACTIONS,
  }));

  r.delete("/api/v1/admin/accounts/{account_id}", "admin.accounts", (ctx): Reply => {
    const account = accountOr404(ctx.params.account_id);
    accounts.splice(accounts.indexOf(account), 1);
    return { status: 204 };
  });

  r.patch("/api/v1/admin/accounts/{account_id}", "admin.accounts", (ctx): Reply => {
    const account = accountOr404(ctx.params.account_id);
    Object.assign(account, definedOnly(bodyOf<S["AccountUpdate"]>(ctx)));
    return { body: account };
  });

  r.put("/api/v1/admin/accounts/{account_id}/bot-token", "admin.accounts", (ctx): Reply => {
    const account = accountOr404(ctx.params.account_id);
    const { token } = bodyOf<S["BotTokenSet"]>(ctx);
    if (token.trim().length < 8) {
      fail(422, "validation_failed", "Token không hợp lệ. Kiểm tra lại với Zalo Bot.");
    }
    account.has_bot_token = true;
    return { body: account };
  });

  r.post("/api/v1/admin/accounts/{account_id}/login", "admin.accounts", (ctx): Reply => {
    const account = accountOr404(ctx.params.account_id);
    if (account.channel !== "zalo_personal") {
      fail(409, "invalid_state", "Chỉ tài khoản Zalo cá nhân đăng nhập bằng mã QR.");
    }
    qrSessions.set(account.id, { polls: 0 });
    return { status: 202, body: qrStatus(account.id) };
  });

  r.get("/api/v1/admin/accounts/{account_id}/login/status", "admin.accounts", (ctx): Reply => ({
    body: qrStatus(accountOr404(ctx.params.account_id).id),
  }));

  r.put("/api/v1/admin/policy/accounts/{account_id}", "admin.policy", (ctx): Reply => {
    const account = accountOr404(ctx.params.account_id);
    account.policy_profile = bodyOf<S["AccountPolicyUpdate"]>(ctx).policy_profile;
    return { body: account };
  });

  // channels
  r.get("/api/v1/admin/channels", "admin.channels", (): Reply => ({ body: channels }));
  r.get("/api/v1/admin/channels/{channel}", "admin.channels", (ctx): Reply => ({
    body: channelOr404(ctx.params.channel),
  }));
  r.put("/api/v1/admin/channels/{channel}", "admin.channels", (ctx): Reply => {
    const channel = channelOr404(ctx.params.channel);
    const { version, ...patch } = bodyOf<S["ChannelSettingsUpdate"]>(ctx);
    if (version !== channel.version) {
      fail(409, "version_conflict", "Kênh vừa được người khác cập nhật. Tải lại rồi thử lại.");
    }
    Object.assign(channel, definedOnly(patch), {
      version: channel.version + 1,
      updated_at: isoFromNow(0),
    });
    return { body: channel };
  });
  r.post("/api/v1/admin/channels/{channel}/kill-switch", "admin.kill_switch", (ctx: Ctx): Reply => {
    const channel = channelOr404(ctx.params.channel);
    const { on, reason } = bodyOf<S["KillSwitchRequest"]>(ctx);
    if (on && !reason?.trim()) fail(422, "validation_failed", "Nhập lý do khi bật công tắc khẩn.");
    Object.assign(channel, {
      kill_switch_on: on,
      kill_switch_reason: on ? (reason ?? null) : null,
      kill_switch_changed_at: isoFromNow(0),
      kill_switch_changed_by: ctx.session?.userId ?? null,
      version: channel.version + 1,
    });
    return { body: channel };
  });

  // friends
  r.get("/api/v1/admin/friends/{account_id}/list", "admin.accounts", (ctx): Reply => {
    const account = accountOr404(ctx.params.account_id);
    if (account.channel !== "zalo_personal" || !account.running) {
      fail(409, "channel_unavailable", "Tài khoản chưa chạy hoặc không phải nick cá nhân.");
    }
    return { body: friends };
  });
  r.get("/api/v1/admin/friends/{account_id}/requests", "admin.accounts", (ctx): Reply => {
    accountOr404(ctx.params.account_id);
    return { body: friendRequests };
  });
  const decide = (ctx: Ctx): Reply => {
    accountOr404(ctx.params.account_id);
    const { uid } = bodyOf<S["FriendDecision"]>(ctx);
    friendRequests = friendRequests.filter((x) => x.from_uid !== uid);
    return { body: {} };
  };
  r.post("/api/v1/admin/friends/{account_id}/accept", "admin.accounts", decide);
  r.post("/api/v1/admin/friends/{account_id}/reject", "admin.accounts", decide);
}
