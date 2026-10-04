// Mock of the doctor-approved message templates (`clinic.message_template`) and the CRM rules.
import { rules, templates } from "../data/clinic";
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

const VERSION_CONFLICT = "Bản ghi vừa được người khác cập nhật. Tải lại rồi thử lại.";

function templateOr404(ctx: Ctx): S["MessageTemplateOut"] {
  const found = templates.find((t) => t.id === ctx.params.template_id);
  if (!found) fail(404, "not_found", "Không tìm thấy mẫu tin nhắn.");
  return found;
}

export function register(r: Router): void {
  r.get("/api/v1/admin/templates", "kb.read", (): Reply => ({ body: templates }));

  r.post("/api/v1/admin/templates", "kb.manage", (ctx): Reply => {
    const input = bodyOf<S["MessageTemplateCreate"]>(ctx);
    if (templates.some((t) => t.template_key === input.template_key)) {
      fail(409, "duplicate_request", "Mã mẫu đã tồn tại. Chọn mã khác.");
    }
    const created: S["MessageTemplateOut"] = {
      id: uid("tpl"),
      template_key: input.template_key,
      title: input.title,
      body: input.body,
      marketing: input.marketing ?? false,
      // A draft is inactive until a doctor approves it.
      active: false,
      approved_at: null,
      approved_by: null,
      version: 1,
    };
    templates.push(created);
    return { status: 201, body: created };
  });

  r.patch("/api/v1/admin/templates/{template_id}", "kb.manage", (ctx): Reply => {
    const tpl = templateOr404(ctx);
    const input = bodyOf<S["MessageTemplateUpdate"]>(ctx);
    if (input.version !== tpl.version) fail(409, "version_conflict", VERSION_CONFLICT);
    const contentChanged =
      (input.body !== undefined && input.body !== null && input.body !== tpl.body) ||
      (input.title !== undefined && input.title !== null && input.title !== tpl.title) ||
      (input.marketing !== undefined &&
        input.marketing !== null &&
        input.marketing !== tpl.marketing);
    if (input.title) tpl.title = input.title;
    if (input.body) tpl.body = input.body;
    if (input.marketing !== undefined && input.marketing !== null) tpl.marketing = input.marketing;
    if (contentChanged) {
      // Editing clears the doctor's sign-off: the new text has not been approved by anyone.
      tpl.approved_at = null;
      tpl.approved_by = null;
      tpl.active = false;
    }
    if (input.active !== undefined && input.active !== null) {
      if (input.active && !tpl.approved_at) {
        fail(409, "invalid_state", "Mẫu chưa được bác sĩ duyệt nên không bật được.");
      }
      tpl.active = input.active;
    }
    tpl.version += 1;
    return { body: tpl };
  });

  r.post(
    "/api/v1/admin/templates/{template_id}/approve",
    "review.decide_clinical",
    (ctx): Reply => {
      const tpl = templateOr404(ctx);
      const input = bodyOf<S["MessageTemplateApprove"]>(ctx);
      if (input.version !== tpl.version) fail(409, "version_conflict", VERSION_CONFLICT);
      tpl.approved_at = isoFromNow(0);
      tpl.approved_by = ctx.session?.userId ?? null;
      tpl.active = true;
      tpl.version += 1;
      return { body: tpl };
    },
  );

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
    if (input.send_mode) rule.send_mode = input.send_mode;
    if (input.suggested_action) rule.suggested_action = input.suggested_action;
    rule.version += 1;
    return { body: rule };
  });
}
