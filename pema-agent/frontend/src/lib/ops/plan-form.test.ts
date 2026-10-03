import { describe, expect, it } from "vitest";

import {
  SERVICE_REQUIRED_MESSAGE,
  TITLE_REQUIRED_MESSAGE,
  TOTAL_BELOW_DONE_MESSAGE,
  TOTAL_RANGE_MESSAGE,
  planStepStates,
  validatePlanForm,
  type PlanFormState,
} from "./plan-form";

const FORM: PlanFormState = {
  title: "Laser CO2 phục hồi da",
  serviceCode: "laser-co2",
  total: "4",
  goal: "",
};

describe("validatePlanForm", () => {
  it("a_named_plan_with_a_sensible_total_has_no_problem", () => {
    expect(validatePlanForm(FORM, 2, false)).toBeNull();
  });

  it("the_name_is_required", () => {
    expect(validatePlanForm({ ...FORM, title: " " }, 0, false)).toBe(TITLE_REQUIRED_MESSAGE);
  });

  it("a_new_plan_needs_its_service_code_but_an_edit_does_not", () => {
    const form = { ...FORM, serviceCode: "" };

    expect([validatePlanForm(form, 0, true), validatePlanForm(form, 0, false)]).toEqual([
      SERVICE_REQUIRED_MESSAGE,
      null,
    ]);
  });

  it.each(["0", "21", "2.5", "abc", ""])("a_total_of_%s_is_out_of_range", (total) => {
    expect(validatePlanForm({ ...FORM, total }, 0, false)).toBe(TOTAL_RANGE_MESSAGE);
  });

  it("the_total_cannot_drop_below_the_sessions_already_done", () => {
    expect(validatePlanForm({ ...FORM, total: "2" }, 3, false)).toBe(TOTAL_BELOW_DONE_MESSAGE);
  });

  it("the_total_may_equal_the_sessions_done", () => {
    expect(validatePlanForm({ ...FORM, total: "3" }, 3, false)).toBeNull();
  });
});

describe("planStepStates", () => {
  it("lists_done_sessions_then_the_next_one_then_the_later_ones", () => {
    expect(planStepStates(2, 5)).toEqual(["done", "done", "next", "later", "later"]);
  });

  it("a_finished_plan_has_no_next_session", () => {
    expect(planStepStates(3, 3)).toEqual(["done", "done", "done"]);
  });
});
