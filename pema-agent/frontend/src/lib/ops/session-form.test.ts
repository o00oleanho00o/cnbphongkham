import { describe, expect, it } from "vitest";

import {
  AFTERCARE_REQUIRED_MESSAGE,
  DATE_INVALID_MESSAGE,
  NOTE_REQUIRED_MESSAGE,
  PHOTO_CONSENT_MESSAGE,
  PLAN_FULL_MESSAGE,
  addDays,
  defaultNextVisit,
  isRealDate,
  sessionCounterLabel,
  stageForNewPhoto,
  validateSessionForm,
  type SessionFormState,
} from "./session-form";

const TODAY = "2026-09-20";

const FILLED: SessionFormState = {
  planId: "plan-1",
  performedOn: TODAY,
  sessionType: "Laser CO2",
  protocolId: "laser-co2",
  nextVisitOn: "2026-10-20",
  note: "Da ổn, đỏ nhẹ giảm.",
  aftercare: "Dưỡng ẩm dịu nhẹ.",
  region: "Mặt",
  view: "Chính diện",
  photoName: "",
  photoConsent: false,
};

const OPEN_PLAN = { completed: 1, total: 4 };

describe("validateSessionForm", () => {
  it("a_complete_form_of_an_open_plan_has_no_problem", () => {
    expect(validateSessionForm(FILLED, OPEN_PLAN, "2026-09-06", TODAY)).toBeNull();
  });

  it("a_plan_with_all_its_sessions_refuses_a_new_one_before_anything_else", () => {
    const form = { ...FILLED, note: "" };

    expect(validateSessionForm(form, { completed: 4, total: 4 }, null, TODAY)).toBe(
      PLAN_FULL_MESSAGE,
    );
  });

  it("the_assessment_is_required", () => {
    expect(validateSessionForm({ ...FILLED, note: "   " }, OPEN_PLAN, null, TODAY)).toBe(
      NOTE_REQUIRED_MESSAGE,
    );
  });

  it("the_aftercare_text_is_required", () => {
    expect(validateSessionForm({ ...FILLED, aftercare: "" }, OPEN_PLAN, null, TODAY)).toBe(
      AFTERCARE_REQUIRED_MESSAGE,
    );
  });

  it.each([
    ["a_date_in_the_future", "2026-09-21", null],
    ["a_date_before_the_previous_session", "2026-09-01", "2026-09-06"],
    ["a_date_that_does_not_exist", "2026-02-30", null],
    ["no_date_at_all", "", null],
  ])("%s_is_refused", (_name, performedOn, lastVisit) => {
    expect(validateSessionForm({ ...FILLED, performedOn }, OPEN_PLAN, lastVisit, TODAY)).toBe(
      DATE_INVALID_MESSAGE,
    );
  });

  it("the_same_day_as_the_previous_session_is_allowed", () => {
    expect(
      validateSessionForm({ ...FILLED, performedOn: "2026-09-06" }, OPEN_PLAN, "2026-09-06", TODAY),
    ).toBeNull();
  });

  it("a_photo_without_the_consent_checkbox_is_refused", () => {
    const form = { ...FILLED, photoName: "anh.jpg", photoConsent: false };

    expect(validateSessionForm(form, OPEN_PLAN, null, TODAY)).toBe(PHOTO_CONSENT_MESSAGE);
  });

  it("a_photo_with_the_consent_checkbox_is_accepted", () => {
    const form = { ...FILLED, photoName: "anh.jpg", photoConsent: true };

    expect(validateSessionForm(form, OPEN_PLAN, null, TODAY)).toBeNull();
  });

  it("a_session_without_a_plan_only_needs_the_text_and_the_date", () => {
    expect(validateSessionForm(FILLED, null, null, TODAY)).toBeNull();
  });
});

describe("sessionCounterLabel", () => {
  it.each([
    [{ completed: 1, total: 4 }, "2/4 dự kiến"],
    [{ completed: 3, total: 4 }, "4/4 dự kiến"],
    [{ completed: 4, total: 4 }, "4/4 · kế hoạch đủ buổi"],
    [null, "Không gắn kế hoạch"],
  ])("%j_reads_%s", (plan, expected) => {
    expect(sessionCounterLabel(plan)).toBe(expected);
  });
});

describe("dates", () => {
  it("the_next_visit_defaults_to_thirty_days_after_today", () => {
    expect(defaultNextVisit(TODAY)).toBe("2026-10-20");
  });

  it("days_are_added_across_a_month_end", () => {
    expect(addDays("2026-12-25", 10)).toBe("2027-01-04");
  });

  it.each([
    ["2026-09-20", true],
    ["2026-9-20", false],
    ["2026-02-29", false],
    ["2028-02-29", true],
  ])("%s_is_a_real_date_%s", (value, expected) => {
    expect(isRealDate(value)).toBe(expected);
  });
});

describe("stageForNewPhoto", () => {
  it("the_first_photo_of_an_angle_is_the_before_and_the_next_ones_are_after", () => {
    expect([stageForNewPhoto(0), stageForNewPhoto(1), stageForNewPhoto(5)]).toEqual([
      "before",
      "after",
      "after",
    ]);
  });
});
