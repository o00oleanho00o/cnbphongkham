import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";

import { POLICY_ROWS } from "./policy-text";

const PATIENT_CHANNEL: Schemas["PolicyProfile"] = {
  key: "patient_channel",
  outbound_mode: "review",
  scheduled_jobs: "message_from_template_only",
  memory_write: "staff_only",
  disabled_tool_keys: ["web_search", "read_image"],
  inbound_media: "flag_and_hand_off",
  red_flag_check: true,
  pii_mask: "required",
  proactive_cap_scope: "patient_account",
  marketing_opt_out_blocks_marketing: true,
  birthday_auto_send: false,
  require_identity_verification: true,
};

const row = (key: string) => POLICY_ROWS.find((r) => r.key === key);

describe("policy profile wording", () => {
  it("review_mode_says_a_person_approves_before_sending", () => {
    expect(row("outbound")?.text(PATIENT_CHANNEL)).toContain("duyệt");
  });

  it("disabled_tools_are_counted", () => {
    expect(row("tools")?.text(PATIENT_CHANNEL)).toBe("Tắt (2 công cụ)");
  });

  it("the_birthday_is_never_sent_automatically_when_the_flag_is_off", () => {
    expect(row("birthday")?.text(PATIENT_CHANNEL)).toContain("Không tự gửi");
  });

  it("a_profile_without_red_flag_check_says_not_applicable", () => {
    expect(row("redflag")?.text({ ...PATIENT_CHANNEL, red_flag_check: false })).toBe(
      "Không áp dụng",
    );
  });

  it("every_field_of_the_table_has_a_row", () => {
    expect(POLICY_ROWS.map((r) => r.key)).toEqual([
      "outbound",
      "scheduled",
      "memory",
      "media",
      "tools",
      "redflag",
      "pii",
      "cap",
      "optout",
      "birthday",
      "identity",
    ]);
  });
});
