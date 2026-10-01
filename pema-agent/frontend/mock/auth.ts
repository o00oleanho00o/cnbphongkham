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
  type Ctx,
  type Permission,
  type Reply,
  type Role,
  type Router,
  type Schemas,
  type Session,
} from "./core";

export const CLINIC_ID = uuid(1, 0);
export const CLINIC_SLUG = "pema-demo";
export const CLINIC_NAME = "Phòng khám Pema (dữ liệu mẫu)";
export const COOKIE = "pema_session";

type MockUser = {
  id: string;
  email: string;
  password: string;
  role: Role;
  display_name: string;
};

/** Synthetic staff. Password is the same for all and printed in the README on purpose. */
export const USERS: MockUser[] = [
  {
    id: uuid(1, 1),
    email: "owner@pema.test",
    password: "demo1234",
    role: "owner",
    display_name: "Nguyễn Thanh Hà",
  },
  {
    id: uuid(2, 1),
    email: "manager@pema.test",
    password: "demo1234",
    role: "manager",
    display_name: "Phạm Quốc Việt",
  },
  {
    id: uuid(3, 1),
    email: "doctor@pema.test",
    password: "demo1234",
    role: "doctor",
    display_name: "BS. Lê Minh Tâm",
  },
  {
    id: uuid(4, 1),
    email: "cs@pema.test",
    password: "demo1234",
    role: "cs_staff",
    display_name: "Mai Anh",
  },
  {
    id: uuid(5, 1),
    email: "reception@pema.test",
    password: "demo1234",
    role: "reception",
    display_name: "Võ Ngọc Trâm",
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
];

export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  // `admin.users` (reset another user's password) is the owner's alone; the manager does not get it.
  owner: [...ALL, "admin.users"],
  manager: ALL,
  doctor: [
    "patient.read",
    "patient.read_360",
    "consent.read",
    "appointment.read",
    "appointment.write",
    "session.write",
    "crm.task.read",
    "conversation.read",
    "review.read",
    "review.decide",
    "review.decide_clinical",
    "kb.read",
  ],
  cs_staff: [
    "patient.read",
    "patient.read_360",
    "consent.read",
    "consent.write",
    "appointment.read",
    "appointment.write",
    "crm.task.read",
    "crm.task.resolve",
    "crm.activity.write",
    "conversation.read",
    "conversation.reply",
    "review.read",
    "review.decide",
    "kb.read",
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

const RESET_LIMIT = 5;
const RESET_WINDOW_MS = 60_000;
const resets = new Map<string, { count: number; resetAt: number }>();

/** 5 resets per minute per owner, like the real route. */
function allowReset(userId: string): boolean {
  const now = Date.now();
  const entry = resets.get(userId);
  if (!entry || now >= entry.resetAt) {
    resets.set(userId, { count: 1, resetAt: now + RESET_WINDOW_MS });
    return true;
  }
  entry.count += 1;
  return entry.count <= RESET_LIMIT;
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
    const { clinic_slug, email, password } = ctx.body as {
      clinic_slug?: string;
      email?: string;
      password?: string;
    };
    const user = USERS.find((u) => u.email === email?.toLowerCase());
    if (clinic_slug !== CLINIC_SLUG || !user || user.password !== password) {
      throw new HttpError(401, "unauthenticated", "Sai phòng khám, email hoặc mật khẩu.");
    }
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
    if (!allowReset(s.userId)) {
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
    for (const [id, other] of sessions) {
      if (other.userId === user.id) sessions.delete(id);
    }
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
