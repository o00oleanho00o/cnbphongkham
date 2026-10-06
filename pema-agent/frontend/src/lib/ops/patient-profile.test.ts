import { describe, expect, it } from "vitest";

import {
  EXPECTED_RETURN_INVALID,
  EXPECTED_SOURCE_OPTIONS,
  alertsProblem,
  expectedReturnProblem,
  isIsoDay,
  parseServicePlanForm,
  splitAlerts,
} from "./patient-profile";

const VALID = {
  date: "2026-10-01",
  reason: "Bác sĩ hẹn đánh giá",
  source: "doctor_recommendation",
};

describe("splitAlerts", () => {
  it("one_warning_per_line_trimmed_with_blank_lines_dropped", () => {
    expect(splitAlerts("  Da nhạy cảm \n\n Theo dõi đỏ da\n   ")).toEqual([
      "Da nhạy cảm",
      "Theo dõi đỏ da",
    ]);
  });

  it("an_empty_box_means_no_warnings", () => {
    expect(splitAlerts("")).toEqual([]);
  });
});

describe("alertsProblem", () => {
  it("accepts_up_to_twenty_lines_of_two_hundred_characters", () => {
    expect(alertsProblem(Array.from({ length: 20 }, () => "x".repeat(200)))).toBeNull();
  });

  it("refuses_a_twenty_first_line_and_a_long_line", () => {
    expect(alertsProblem(Array.from({ length: 21 }, () => "x"))).toBe("Tối đa 20 cảnh báo.");
    expect(alertsProblem(["x".repeat(201)])).toBe("Mỗi cảnh báo tối đa 200 ký tự.");
  });
});

describe("isIsoDay", () => {
  it("accepts_a_real_day_and_refuses_an_impossible_or_badly_written_one", () => {
    expect(isIsoDay("2026-02-28")).toBe(true);
    expect(isIsoDay("2028-02-29")).toBe(true);
    expect(isIsoDay("2026-02-30")).toBe(false);
    expect(isIsoDay("20/09/2026")).toBe(false);
    expect(isIsoDay("")).toBe(false);
  });
});

describe("expectedReturnProblem", () => {
  it("a_complete_form_has_no_problem", () => {
    expect(expectedReturnProblem(VALID)).toBeNull();
  });

  it.each([
    ["an_impossible_date", { ...VALID, date: "2026-02-30" }],
    ["a_blank_reason", { ...VALID, reason: "   " }],
    ["the_appointment_source", { ...VALID, source: "appointment" }],
    ["an_unknown_source", { ...VALID, source: "made_up" }],
  ])("says_the_old_sentence_for_%s", (_name, form) => {
    expect(expectedReturnProblem(form)).toBe(EXPECTED_RETURN_INVALID);
  });

  it("offers_the_four_sources_a_person_may_type_in_the_words_of_the_old_web", () => {
    expect(EXPECTED_SOURCE_OPTIONS.map((o) => o.label)).toEqual([
      "Bác sĩ khuyến nghị",
      "Protocol dịch vụ",
      "Kế hoạch điều trị",
      "Chăm sóc sau điều trị",
    ]);
  });
});

describe("parseServicePlanForm", () => {
  const form = { serviceId: "svc-1", sessions: "3", discount: "500000" };

  it("builds_the_body_of_the_request", () => {
    expect(parseServicePlanForm(form)).toEqual({
      ok: true,
      body: { service_id: "svc-1", sessions: 3, discount_vnd: 500000 },
    });
  });

  it("an_empty_discount_is_zero", () => {
    expect(parseServicePlanForm({ ...form, discount: " " })).toEqual({
      ok: true,
      body: { service_id: "svc-1", sessions: 3, discount_vnd: 0 },
    });
  });

  it.each([
    ["no_service", { ...form, serviceId: "" }],
    ["zero_sessions", { ...form, sessions: "0" }],
    ["twenty_one_sessions", { ...form, sessions: "21" }],
    ["a_fractional_session_count", { ...form, sessions: "1.5" }],
    ["a_negative_discount", { ...form, discount: "-1" }],
  ])("refuses_%s", (_name, bad) => {
    expect(parseServicePlanForm(bad).ok).toBe(false);
  });
});
