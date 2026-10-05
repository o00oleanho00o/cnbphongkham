// Mock of the staff accounts of the clinic: list, create, edit and lock. It behaves like the real routes
// (backend tests/api/test_admin_users_routes.py): the manager LISTS (`admin.users.read`), only the owner changes
// (`admin.users`, from the permission table of mock/auth.ts); 409 for a taken e-mail and a stale version, 422 for a
// bad body, your own account and the last active owner, 429 after 5 creations a minute per owner, 404 for an
// unknown id; a lock or a role change ends every session of that user; a locked account cannot sign in.
import { USERS, allowAttempt, revokeSessionsOf, type MockUser } from "../auth";
import {
  bodyOf,
  fail,
  isoFromNow,
  paginate,
  uuid,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;
type StaffRole = Exclude<S["Role"], "patient">;

const STAFF_ROLES: readonly StaffRole[] = [
  "owner",
  "manager",
  "doctor",
  "cs_staff",
  "reception",
  "accountant",
];
const MIN_PASSWORD = 8;
const VERSION_CONFLICT = "Bản ghi đã được người khác thay đổi. Hãy tải lại rồi thử lại.";
const NOT_FOUND = "Không tìm thấy tài khoản.";

let created = 0;

function staffOut(u: MockUser): S["StaffUserOut"] {
  return {
    id: u.id,
    display_name: u.display_name,
    email: u.email,
    role: u.role,
    active: u.active,
    last_login_at: u.last_login_at,
    created_at: u.created_at,
    version: u.version,
  };
}

function isStaffRole(role: unknown): role is StaffRole {
  return typeof role === "string" && (STAFF_ROLES as readonly string[]).includes(role);
}

function userOr404(ctx: Ctx): MockUser {
  const found = USERS.find((u) => u.id === ctx.params.user_id && isStaffRole(u.role));
  if (!found) fail(404, "not_found", NOT_FOUND);
  return found;
}

function activeOwners(): MockUser[] {
  return USERS.filter((u) => u.role === "owner" && u.active);
}

export function register(r: Router): void {
  r.get("/api/v1/admin/users", "admin.users.read", (ctx): Reply => {
    const q = (ctx.query.get("q") ?? "").trim().toLowerCase();
    const role = ctx.query.get("role");
    const active = ctx.query.get("active");
    const rows = USERS.filter((u) => isStaffRole(u.role))
      .filter((u) => !role || u.role === role)
      .filter((u) => active === null || String(u.active) === active)
      .filter(
        (u) => !q || u.display_name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
      )
      .sort((a, b) => a.display_name.localeCompare(b.display_name, "vi"));
    return { body: paginate(rows.map(staffOut), ctx.query) };
  });

  r.post("/api/v1/admin/users", "admin.users", (ctx): Reply => {
    const s = ctx.session;
    if (!s) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
    if (!allowAttempt("create", s.userId)) {
      fail(429, "rate_limited", "Tạo tài khoản quá nhiều lần. Vui lòng đợi một phút.");
    }
    const input = bodyOf<Partial<S["StaffUserCreate"]>>(ctx);
    const email = (input.email ?? "").trim().toLowerCase();
    const name = (input.display_name ?? "").trim();
    if (!name) fail(422, "validation_failed", "Hãy nhập họ tên.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      fail(422, "validation_failed", "Email đăng nhập chưa đúng dạng.");
    }
    if (!isStaffRole(input.role)) {
      fail(422, "validation_failed", "Vai trò này không dành cho nhân viên.");
    }
    if (typeof input.password !== "string" || input.password.length < MIN_PASSWORD) {
      fail(422, "validation_failed", `Mật khẩu cần ít nhất ${MIN_PASSWORD} ký tự.`);
    }
    if (USERS.some((u) => u.email === email)) {
      fail(
        409,
        "invalid_state",
        "Email đăng nhập này đã được dùng trong phòng khám. Hãy chọn email khác.",
      );
    }
    created += 1;
    const user: MockUser = {
      id: uuid(100 + created, 1),
      email,
      password: input.password,
      role: input.role,
      display_name: name,
      active: true,
      created_at: isoFromNow(0),
      last_login_at: null,
      version: 1,
    };
    USERS.push(user);
    return { status: 201, body: staffOut(user) };
  });

  r.patch("/api/v1/admin/users/{user_id}", "admin.users", (ctx): Reply => {
    const s = ctx.session;
    if (!s) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
    const input = bodyOf<Partial<S["StaffUserUpdate"]>>(ctx);
    if (
      input.display_name === undefined &&
      input.role === undefined &&
      input.active === undefined
    ) {
      fail(422, "validation_failed", "Không có thay đổi nào để lưu.");
    }
    if (input.role !== undefined && input.role !== null && !isStaffRole(input.role)) {
      fail(422, "validation_failed", "Vai trò này không dành cho nhân viên.");
    }
    const user = userOr404(ctx);
    if (input.version !== user.version) fail(409, "version_conflict", VERSION_CONFLICT);

    const own = user.id === s.userId;
    const roleChanges = isStaffRole(input.role) && input.role !== user.role;
    const lockChanges = typeof input.active === "boolean" && input.active !== user.active;
    const selfProtected = own && (roleChanges || (lockChanges && input.active === false));
    if (selfProtected) {
      fail(422, "validation_failed", "Bạn không thể tự khóa hoặc tự đổi vai trò của chính mình.");
    }
    const leavesOwners =
      user.role === "owner" &&
      user.active &&
      ((roleChanges && input.role !== "owner") || (lockChanges && input.active === false));
    if (leavesOwners && activeOwners().filter((o) => o.id !== user.id).length === 0) {
      fail(
        422,
        "validation_failed",
        "Phòng khám phải luôn có ít nhất một chủ phòng khám đang hoạt động.",
      );
    }

    const name = typeof input.display_name === "string" ? input.display_name.trim() : "";
    const nameChanges = name !== "" && name !== user.display_name;
    if (!nameChanges && !roleChanges && !lockChanges) return { body: staffOut(user) };
    if (nameChanges) user.display_name = name;
    if (roleChanges && isStaffRole(input.role)) user.role = input.role;
    if (lockChanges && typeof input.active === "boolean") user.active = input.active;
    user.version += 1;
    if (roleChanges || (lockChanges && input.active === false)) revokeSessionsOf(user.id);
    return { body: staffOut(user) };
  });
}
