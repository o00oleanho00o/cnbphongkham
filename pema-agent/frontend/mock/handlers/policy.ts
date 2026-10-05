// Mock of the policy profiles (as data) and the zalo_uid <-> patient identity confirmation.
// `PUT /admin/policy/accounts/{account_id}` belongs to the accounts mock (it owns the accounts).
import { patientRef } from "../data/clinic";
import { bodyOf, fail, isoFromNow, type Reply, type Router, type Schemas } from "../core";

type S = Schemas;

const MEDIA_AND_WEB_TOOLS = [
  "send_file",
  "create_word_document",
  "create_excel_file",
  "create_image",
  "tai_video",
  "read_image",
  "web_search",
  "web_fetch",
];

const PROFILES: S["PolicyProfile"][] = [
  {
    key: "staff_assistant",
    outbound_mode: "direct",
    scheduled_jobs: "any",
    memory_write: "allow",
    disabled_tool_keys: [],
    inbound_media: "pass",
    red_flag_check: false,
    pii_mask: "optional",
    proactive_cap_scope: "account_thread",
    marketing_opt_out_blocks_marketing: true,
    birthday_auto_send: false,
    require_identity_verification: false,
  },
  {
    key: "patient_channel",
    outbound_mode: "review",
    scheduled_jobs: "message_from_template_only",
    memory_write: "staff_only",
    disabled_tool_keys: MEDIA_AND_WEB_TOOLS,
    inbound_media: "flag_and_hand_off",
    red_flag_check: true,
    pii_mask: "required",
    proactive_cap_scope: "patient_account",
    marketing_opt_out_blocks_marketing: true,
    birthday_auto_send: false,
    require_identity_verification: true,
  },
];

const pending: S["IdentityLink"][] = [
  {
    channel: "zalo_bot",
    external_user_id: "u-demo-004",
    patient_id: patientRef(7).id,
    patient_code: patientRef(7).code,
    status: "pending",
    verified_at: null,
  },
  {
    channel: "zalo_bot",
    external_user_id: "u-demo-009",
    patient_id: patientRef(9).id,
    patient_code: patientRef(9).code,
    status: "pending",
    verified_at: null,
  },
  {
    channel: "zalo_personal",
    external_user_id: "u-demo-011",
    patient_id: null,
    patient_code: null,
    status: "unlinked",
    verified_at: null,
  },
];

export function register(r: Router): void {
  r.get("/api/v1/admin/policy/profiles", "admin.policy", (): Reply => ({
    body: { profiles: PROFILES } satisfies S["PolicyProfilesOut"],
  }));

  r.get("/api/v1/admin/policy/identity/pending", "admin.policy", (): Reply => ({
    body: pending,
  }));

  r.post("/api/v1/admin/policy/identity/confirm", "admin.policy", (ctx): Reply => {
    const input = bodyOf<S["IdentityConfirm"]>(ctx);
    const index = pending.findIndex(
      (p) => p.channel === input.channel && p.external_user_id === input.external_user_id,
    );
    const link = pending[index];
    if (!link) fail(404, "not_found", "Không tìm thấy yêu cầu xác minh này.");
    const decided: S["IdentityLink"] = {
      ...link,
      patient_id: input.patient_id,
      status: input.reject ? "rejected" : "verified",
      verified_at: input.reject ? null : isoFromNow(0),
    };
    pending.splice(index, 1);
    return { body: decided };
  });
}
