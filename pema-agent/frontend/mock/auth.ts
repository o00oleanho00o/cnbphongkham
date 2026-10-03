// Mock sign-in, session cookie and the role -> permission table. The table is a SIMULATION of the
// ARCH-PB01 matrix (the real one is implemented by package B1); it exists so each role sees the menu
// it would see and the 403 state can be exercised.
import { randomUUID } from "node:crypto";

import {
  HttpError,
  fail,
  isoFromNow,
  uuid,
  DAY,
  HOUR,
  MIN,
  type Ctx,
  type Permission,
  type Reply,
  type Role,
  type Router,
  type Schemas,
  type Session,
} from "./core";

export const CLINIC_ID = uuid(1, 0);
export const CLINIC_NAME = "Phòng khám Pema (dữ liệu mẫu)";
export const COOKIE = "pema_session";

export type MockUser = {
  id: string;
  email: string;
  password: string;
  role: Role;
  display_name: string;
  /** false = locked by the owner: cannot sign in, every session ended. */
  active: boolean;
  created_at: string;
  last_login_at: string | null;
  /** Optimistic lock of the staff screen (`PATCH /admin/users/{user_id}`). */
  version: number;
};

/** Synthetic staff. Password is the same for all and printed in the README on purpose. */
export const USERS: MockUser[] = [
  {
    id: uuid(1, 1),
    email: "owner@pema.test",
    password: "demo1234",
    role: "owner",
    display_name: "Nguyễn Thanh Hà",
    active: true,
    created_at: isoFromNow(-240 * DAY),
    last_login_at: isoFromNow(-2 * MIN),
    version: 1,
  },
  {
    id: uuid(2, 1),
    email: "manager@pema.test",
    password: "demo1234",
    role: "manager",
    display_name: "Phạm Quốc Việt",
    active: true,
    created_at: isoFromNow(-200 * DAY),
    last_login_at: isoFromNow(-3 * HOUR),
    version: 1,
  },
  {
    id: uuid(3, 1),
    email: "doctor@pema.test",
    password: "demo1234",
    role: "doctor",
    display_name: "BS. Lê Minh Tâm",
    active: true,
    created_at: isoFromNow(-180 * DAY),
    last_login_at: isoFromNow(-26 * HOUR),
    version: 1,
  },
  {
    id: uuid(4, 1),
    email: "cs@pema.test",
    password: "demo1234",
    role: "cs_staff",
    display_name: "Mai Anh",
    active: true,
    created_at: isoFromNow(-150 * DAY),
    last_login_at: isoFromNow(-50 * MIN),
    version: 1,
  },
  {
    id: uuid(5, 1),
    email: "reception@pema.test",
    password: "demo1234",
    role: "reception",
    display_name: "Võ Ngọc Trâm",
    active: true,
    created_at: isoFromNow(-120 * DAY),
    last_login_at: isoFromNow(-5 * DAY),
    version: 1,
  },
  {
    id: uuid(11, 1),
    email: "bsan@pema.test",
    password: "demo1234",
    role: "doctor",
    display_name: "BS. Trương Hoài An",
    active: true,
    created_at: isoFromNow(-90 * DAY),
    last_login_at: isoFromNow(-2 * DAY),
    version: 1,
  },
  {
    id: uuid(6, 1),
    email: "thu@pema.test",
    password: "demo1234",
    role: "cs_staff",
    display_name: "Đặng Minh Thư",
    active: true,
    created_at: isoFromNow(-60 * DAY),
    last_login_at: null,
    version: 1,
  },
  {
    id: uuid(7, 1),
    email: "lan@pema.test",
    password: "demo1234",
    role: "reception",
    display_name: "Bùi Ngọc Lan",
    active: false,
    created_at: isoFromNow(-300 * DAY),
    last_login_at: isoFromNow(-70 * DAY),
    version: 2,
  },
];

const ALL: Permission[] = [
  "patient.read",
  "patient.write",
  "patient.read_360",
  "consent.read",
  "consent.write",
  "appointment.read",
  "appointment.write",
  "appointment.check_in",
  "session.write",
  "crm.task.read",
  "crm.task.resolve",
  "crm.activity.write",
  "conversation.read",
  "conversation.reply",
  "review.read",
  "review.decide",
  "review.decide_clinical",
  "kb.read",
  "kb.manage",
  "admin.rules",
  "admin.channels",
  "admin.kill_switch",
  "admin.logs",
  "admin.accounts",
  "admin.agents",
  "admin.model",
  "admin.tools",
  "admin.schedules",
  "admin.mcp",
  "admin.usage",
  "admin.policy",
  // The manager LISTS staff (`GET /admin/users`); changing them is `admin.users`, the owner's alone.
  "admin.users.read",
  "care.read",
  "care.act",
  "care.admin",
  "care.matrix",
  "care.approve",
];

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  // `admin.users` (reset another user's password) is the owner's alone; the manager does not get it.
  // Clinical reads and photos (package U3): owner, doctor and care staff; a manager is not a clinician and holds no
  // `session.write` either (the BE matrix), so the mock takes it out of the shared list.
  owner: [...ALL, "admin.users", "session.read", "media.read", "media.write"],
  manager: ALL.filter((permission) => permission !== "session.write"),
  doctor: [
    "patient.read",
    "patient.read_360",
    "consent.read",
    "consent.write",
    "appointment.read",
    "appointment.write",
    "appointment.check_in",
    "session.write",
    "session.read",
    "media.read",
    "media.write",
    "crm.task.read",
    "conversation.read",
    "review.read",
    "review.decide",
    "review.decide_clinical",
    "kb.read",
    "care.read",
    "care.act",
    "care.matrix",
    "care.approve",
  ],
  cs_staff: [
    "patient.read",
    "patient.read_360",
    "session.read",
    "media.read",
    "media.write",
    "consent.read",
    "consent.write",
    "appointment.read",
    "crm.task.read",
    "crm.task.resolve",
    "crm.activity.write",
    "conversation.read",
    "conversation.reply",
    "review.read",
    "review.decide",
    "kb.read",
    "care.read",
    "care.act",
  ],
  reception: [
    "patient.read",
    "appointment.read",
    "appointment.write",
    "appointment.check_in",
    "crm.task.read",
    "conversation.read",
    "kb.read",
  ],
  patient: [],
};

const sessions = new Map<string, Session>();

const ATTEMPT_LIMIT = 5;
const ATTEMPT_WINDOW_MS = 60_000;
const attempts = new Map<string, { count: number; resetAt: number }>();

/** 5 attempts per minute per owner and kind of action (`reset`, `create`), like the real routes. */
export function allowAttempt(kind: string, userId: string): boolean {
  const key = `${kind}:${userId}`;
  const now = Date.now();
  const entry = attempts.get(key);
  if (!entry || now >= entry.resetAt) {
    attempts.set(key, { count: 1, resetAt: now + ATTEMPT_WINDOW_MS });
    return true;
  }
  entry.count += 1;
  return entry.count <= ATTEMPT_LIMIT;
}

/** Forget every attempt (tests share one minute; the dev mock never calls it). */
export function resetAttempts(): void {
  attempts.clear();
}

/** End every session of a user (a lock, a role change, a password reset). */
export function revokeSessionsOf(userId: string): void {
  for (const [id, other] of sessions) {
    if (other.userId === userId) sessions.delete(id);
  }
}

export function userSummary(userId: string): Schemas["UserSummary"] {
  const u = USERS.find((x) => x.id === userId);
  if (!u) fail(401, "unauthenticated", "Phiên đăng nhập không còn hiệu lực.");
  return {
    clinic_id: CLINIC_ID,
    clinic_name: CLINIC_NAME,
    display_name: u.display_name,
    id: u.id,
    role: u.role,
  };
}

export function sessionFromRequest(cookieHeader: string | undefined): Session | null {
  if (!cookieHeader) return null;
  for (const part of cookieHeader.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === COOKIE) return sessions.get(rest.join("=")) ?? null;
  }
  return null;
}

function requireSession(ctx: Ctx): Session {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

export function register(r: Router): void {
  r.post("/api/v1/auth/login", null, (ctx): Reply => {
    // One installation is ONE clinic: the body is e-mail + password. A leftover `clinic_slug` from an old
    // client is accepted and ignored, so nothing breaks while both sides are being changed.
    const { email, password } = ctx.body as {
      email?: string;
      password?: string;
    };
    const user = USERS.find((u) => u.email === email?.toLowerCase());
    // A locked account is refused exactly like a wrong password (no hint that the account exists).
    if (!user || !user.active || user.password !== password) {
      throw new HttpError(401, "unauthenticated", "Sai email hoặc mật khẩu.");
    }
    user.last_login_at = isoFromNow(0);
    const id = randomUUID();
    sessions.set(id, {
      id,
      userId: user.id,
      role: user.role,
      permissions: ROLE_PERMISSIONS[user.role],
    });
    const body: Schemas["SessionInfo"] = {
      expires_at: isoFromNow(DAY),
      user: userSummary(user.id),
    };
    return {
      body,
      headers: { "set-cookie": `${COOKIE}=${id}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400` },
    };
  });

  r.post("/api/v1/auth/logout", null, (ctx): Reply => {
    if (ctx.session) sessions.delete(ctx.session.id);
    return {
      status: 204,
      headers: { "set-cookie": `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0` },
    };
  });

  r.post("/api/v1/auth/refresh", null, (ctx): Reply => {
    const s = requireSession(ctx);
    const body: Schemas["SessionInfo"] = {
      expires_at: isoFromNow(DAY),
      user: userSummary(s.userId),
    };
    return { body };
  });

  // Mirrors the real route: needs the current password, 8-character floor, must differ, every OTHER session
  // of the user ends, the session that made the change keeps working (204, same cookie).
  r.post("/api/v1/auth/password", null, (ctx): Reply => {
    const s = requireSession(ctx);
    const { current_password, new_password } = ctx.body as {
      current_password?: string;
      new_password?: string;
    };
    const user = USERS.find((u) => u.id === s.userId);
    if (!user) fail(401, "unauthenticated", "Phiên đăng nhập không còn hiệu lực.");
    if (user.password !== current_password) {
      fail(401, "unauthenticated", "Mật khẩu hiện tại không đúng.");
    }
    if (typeof new_password !== "string" || new_password.length < 8) {
      fail(422, "validation_failed", "Mật khẩu mới cần ít nhất 8 ký tự.");
    }
    if (new_password === user.password) {
      fail(422, "validation_failed", "Mật khẩu mới phải khác mật khẩu hiện tại.");
    }
    user.password = new_password;
    for (const [id, other] of sessions) {
      if (other.userId === user.id && id !== s.id) sessions.delete(id);
    }
    return { status: 204 };
  });

  // Mirrors the real route (backend test tests/api/test_admin_users_password_route.py): owner only (403 from
  // the permission table), unknown user 404, not your own account (422), 8-character floor (422), at most 5
  // resets per minute per owner (429), every session of the reset user ends, 204 and no body.
  r.post("/api/v1/admin/users/{user_id}/password", "admin.users", (ctx): Reply => {
    const s = requireSession(ctx);
    if (!allowAttempt("reset", s.userId)) {
      fail(429, "rate_limited", "Đặt lại mật khẩu quá nhiều lần. Vui lòng đợi một phút.");
    }
    const { new_password } = ctx.body as { new_password?: string };
    if (ctx.params.user_id === s.userId) {
      fail(422, "validation_failed", "Hãy dùng chức năng đổi mật khẩu của chính bạn.");
    }
    if (typeof new_password !== "string" || new_password.length < 8) {
      fail(422, "validation_failed", "Mật khẩu mới cần ít nhất 8 ký tự.");
    }
    const user = USERS.find((u) => u.id === ctx.params.user_id);
    if (!user) fail(404, "not_found", "Không tìm thấy tài khoản.");
    user.password = new_password;
    revokeSessionsOf(user.id);
    return { status: 204 };
  });

  r.get("/api/v1/me", null, (ctx): Reply => {
    const s = requireSession(ctx);
    const body: Schemas["MeResponse"] = {
      permissions: [...s.permissions],
      user: userSummary(s.userId),
    };
    return { body };
  });

  r.get("/api/v1/permissions", null, (ctx): Reply => {
    const s = requireSession(ctx);
    const body: Schemas["PermissionsResponse"] = { permissions: [...s.permissions], role: s.role };
    return { body };
  });

  r.get("/healthz", null, (): Reply => ({ body: { status: "ok", version: "mock" } }));
}
