// New in Pema: guards the wording of the policy profiles shown to the operator.
import assert from "node:assert/strict";
import { describe, it } from "vitest";

import {
  CANH_BAO_HO_SO,
  HO_SO_MAC_DINH,
  MO_TA_HO_SO,
  NHAN_HO_SO,
} from "@/lib/admin/accounts/policy-profile-text";

describe("policy_profile_text", () => {
  it("default_profile_is_the_patient_channel", () => {
    assert.equal(HO_SO_MAC_DINH, "patient_channel");
  });

  it("each_profile_has_a_label_and_exactly_two_explanation_lines", () => {
    assert.deepEqual(Object.keys(NHAN_HO_SO).sort(), ["patient_channel", "staff_assistant"]);
    assert.equal(MO_TA_HO_SO.patient_channel.length, 2);
    assert.equal(MO_TA_HO_SO.staff_assistant.length, 2);
  });

  it("patient_channel_text_says_review_first_and_red_flags_go_to_a_doctor", () => {
    const text = MO_TA_HO_SO.patient_channel.join(" ");
    assert.match(text, /hàng đợi duyệt/);
    assert.match(text, /cờ đỏ/);
    assert.match(text, /bác sĩ/);
    assert.match(text, /che/);
  });

  it("staff_assistant_text_says_it_sends_directly", () => {
    assert.match(MO_TA_HO_SO.staff_assistant.join(" "), /GỬI THẲNG/);
  });

  it("warning_keeps_patient_accounts_on_the_patient_channel_profile", () => {
    assert.match(CANH_BAO_HO_SO, /BỆNH NHÂN/);
    assert.match(CANH_BAO_HO_SO, /Kênh bệnh nhân/);
  });
});
