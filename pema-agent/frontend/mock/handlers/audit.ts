// Mock of the audit log (admin.logs). The rows are fictional and carry no message text of a patient.
import { CLINIC_ID, USERS } from "../auth";
import { MIN, isoFromNow, paginate, type Reply, type Router, type Schemas } from "../core";

type S = Schemas;

const audit: S["AuditLogOut"][] = Array.from({ length: 70 }, (_, i) => {
  const user = USERS[i % USERS.length];
  const actions = [
    ["auth.login", "session"],
    ["crm.task.resolve", "crm_task"],
    ["appointment.confirm", "appointment"],
    ["consent.update", "consent"],
    ["order.approve", "order"],
    ["finance.payment.record", "payment"],
  ] as const;
  const [action, entity] = actions[i % actions.length] ?? actions[0];
  return {
    id: 1000 - i,
    occurred_at: isoFromNow(-i * 23 * MIN),
    action,
    entity_type: entity,
    entity_id: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
    actor_type: "user",
    actor_role: user?.role ?? null,
    actor_user_id: user?.id ?? null,
    details: { clinic_id: CLINIC_ID, via: "mock" },
    request_id: `req-${i}`,
  };
});

export function register(r: Router): void {
  r.get("/api/v1/admin/logs/audit", "admin.logs", (ctx): Reply => {
    const action = ctx.query.get("action");
    const entity = ctx.query.get("entity_type");
    const found = audit
      .filter((a) => !action || a.action.includes(action))
      .filter((a) => !entity || a.entity_type === entity);
    return { body: paginate(found, ctx.query) };
  });
}
