// Mock of the staff pickers (backend pema/api/routers/staff.py):
//   GET /api/v1/staff/assignable   [{id, name, role}] for EVERY signed-in staff member
// The rule for who is listed is in mock/assignable.ts. The real route is also limited to 60 calls a minute per
// user; the mock does not count (its only limiter is the 5-a-minute one of the password routes).
import { assignableUsers } from "../assignable";
import { fail, type Ctx, type Reply, type Router, type Schemas } from "../core";

export function register(r: Router): void {
  r.get("/api/v1/staff/assignable", null, (ctx: Ctx): Reply => {
    if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
    const staff: Schemas["AssignableStaffOut"][] = assignableUsers().map((u) => ({
      id: u.id,
      name: u.display_name,
      role: u.role,
    }));
    return { body: staff };
  });
}
