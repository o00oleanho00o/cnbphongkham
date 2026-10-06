// Mock of the notifications of the shared inbox (package O, step O3): the operator's own notices, the one-time
// code that links a personal Zalo, quiet hours, push tokens and the clinic settings. No code or token of the
// real chain: the one-time code is made up and expires after ten minutes.
import { accounts } from "./accounts";
import { CODE_TTL_MS, identityPurpose, notifyOf, notifySettings, pushTokens } from "../data/ops";
import {
  bodyOf,
  fail,
  isoFromNow,
  uid,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;

function me(ctx: Ctx): string {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session.userId;
}

function internalLabel(): string | null {
  const internal = accounts.find((a) => a.enabled && identityPurpose.get(a.id) === "internal");
  return internal?.label ?? null;
}

function newCode(): string {
  const tail = Math.random().toString(36).slice(2, 6).toUpperCase().padEnd(4, "K");
  return `PEMA-${tail}`;
}

/** The mock plays the operator: a pending code counts as sent a few seconds after it was made. */
const SENT_AFTER_MS = 8000;

function linkStatus(userId: string): S["NotifyLinkStatus"] {
  const state = notifyOf(userId);
  const code = state.code;
  const age = code ? Date.now() - (code.expiresAt - CODE_TTL_MS) : 0;
  if (code && age >= SENT_AFTER_MS && code.expiresAt > Date.now()) {
    state.linkedAt = isoFromNow(0);
    state.code = null;
  }
  return { linked: state.linkedAt !== null, consented_at: state.linkedAt };
}

function setPreferences(ctx: Ctx): Reply {
  const state = notifyOf(me(ctx));
  const { quiet_start: start, quiet_end: end } = bodyOf<S["NotifyPreferenceIn"]>(ctx);
  const both = Boolean(start) === Boolean(end);
  if (!both)
    fail(422, "validation_failed", "Nhập cả giờ bắt đầu và giờ kết thúc, hoặc để trống cả hai.");
  if ((start && !TIME.test(start)) || (end && !TIME.test(end))) {
    fail(422, "validation_failed", "Giờ phải có dạng HH:MM.");
  }
  if (start && start === end) fail(422, "validation_failed", "Hai mốc giờ phải khác nhau.");
  state.quietStart = start ?? null;
  state.quietEnd = end ?? null;
  return { body: { quiet_start: state.quietStart, quiet_end: state.quietEnd } };
}

export function register(r: Router): void {
  r.get("/api/v1/me/notifications", "notify.self", (ctx): Reply => {
    me(ctx);
    const none: S["NoticeOut"][] = [];
    return { body: none };
  });

  r.post("/api/v1/notifications/ack", "notify.self", (ctx): Reply => {
    me(ctx);
    return { body: { acked: 0 } };
  });

  r.post("/api/v1/notifications/{notification_id}/ack", "notify.self", (): Reply =>
    fail(404, "not_found", "Không tìm thấy thông báo."),
  );

  r.post("/api/v1/me/push-tokens", "notify.self", (ctx): Reply => {
    const userId = me(ctx);
    const { platform } = bodyOf<S["PushTokenIn"]>(ctx);
    const created = { id: uid("push"), platform, last_seen: isoFromNow(0) };
    pushTokens.set(userId, [...(pushTokens.get(userId) ?? []), created]);
    return { body: created };
  });

  r.delete("/api/v1/me/push-tokens/{token_id}", "notify.self", (ctx): Reply => {
    const userId = me(ctx);
    const others = (pushTokens.get(userId) ?? []).filter((t) => t.id !== ctx.params.token_id);
    pushTokens.set(userId, others);
    return { status: 204 };
  });

  r.get("/api/v1/me/notify-zalo", "notify.self", (ctx): Reply => ({ body: linkStatus(me(ctx)) }));

  r.post("/api/v1/me/notify-zalo/link", "notify.self", (ctx): Reply => {
    const state = notifyOf(me(ctx));
    const value = newCode();
    const expiresAt = Date.now() + CODE_TTL_MS;
    state.code = { value, expiresAt };
    return {
      body: {
        code: value,
        expires_at: new Date(expiresAt).toISOString(),
        internal_label: internalLabel(),
      },
    };
  });

  r.delete("/api/v1/me/notify-zalo", "notify.self", (ctx): Reply => {
    const userId = me(ctx);
    const state = notifyOf(userId);
    state.linkedAt = null;
    state.code = null;
    return { body: linkStatus(userId) };
  });

  r.get("/api/v1/me/notify-preferences", "notify.self", (ctx): Reply => {
    const state = notifyOf(me(ctx));
    return { body: { quiet_start: state.quietStart, quiet_end: state.quietEnd } };
  });

  r.put("/api/v1/me/notify-preferences", "notify.self", setPreferences);

  r.get("/api/v1/notifications/settings", "notify.self", (): Reply => ({ body: notifySettings }));

  r.put("/api/v1/notifications/settings", "notify.manage", (ctx): Reply => {
    const input = bodyOf<S["NotifySettingsUpdate"]>(ctx);
    const timeout = input.ack_timeout_s;
    if (timeout !== undefined && timeout !== null && (timeout < 30 || timeout > 3600)) {
      fail(422, "validation_failed", "Thời gian chờ xác nhận phải từ 30 giây đến 60 phút.");
    }
    Object.entries(input).forEach(([key, value]) => {
      if (value === undefined) return;
      Object.assign(notifySettings, { [key]: value });
    });
    return { body: notifySettings };
  });
}
