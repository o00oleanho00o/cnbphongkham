// Mock of the CRM rules (`clinic.crm_rule`): a rule only creates a task for staff.
import { rules } from "../data/clinic";
import {
  bodyOf,
  fail,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const VERSION_CONFLICT = "Bản ghi vừa được người khác cập nhật. Tải lại rồi thử lại.";

export function register(r: Router): void {
  r.get("/api/v1/admin/rules", "admin.rules", (): Reply => ({ body: rules }));
  r.patch("/api/v1/admin/rules/{rule_key}", "admin.rules", (ctx): Reply => {
    const rule = rules.find((x) => x.rule_key === ctx.params.rule_key);
    if (!rule) fail(404, "not_found", "Không tìm thấy quy tắc.");
    const input = bodyOf<S["CrmRuleUpdate"]>(ctx);
    if (input.version !== rule.version) fail(409, "version_conflict", VERSION_CONFLICT);
    if (input.active !== undefined && input.active !== null) rule.active = input.active;
    if (input.delay_days !== undefined && input.delay_days !== null)
      rule.delay_days = input.delay_days;
    if (input.priority) rule.priority = input.priority;
    if (input.suggested_action) rule.suggested_action = input.suggested_action;
    rule.version += 1;
    return { body: rule };
  });
}
