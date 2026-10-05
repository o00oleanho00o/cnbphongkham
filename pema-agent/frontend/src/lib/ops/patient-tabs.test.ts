import { describe, expect, it } from "vitest";

import type { Permission } from "@/lib/session/session-context";

import { visiblePatientTabs } from "./patient-tabs";

const holding =
  (...granted: Permission[]) =>
  (permission: Permission): boolean =>
    granted.includes(permission);

const idsFor = (...granted: Permission[]): string[] =>
  visiblePatientTabs(holding(...granted)).map((tab) => tab.id);

describe("visiblePatientTabs", () => {
  it("a_doctor_sees_all_six_tabs_in_the_order_of_the_old_web", () => {
    expect(idsFor("patient.read_360", "session.read", "media.read")).toEqual([
      "overview",
      "consult",
      "plan",
      "session",
      "photos",
      "finance",
    ]);
  });

  it("a_manager_sees_the_overview_the_plan_and_the_services_and_finance_tab", () => {
    expect(idsFor("patient.read_360")).toEqual(["overview", "plan", "finance"]);
  });

  it("care_staff_with_the_clinical_read_permissions_see_all_tabs_too", () => {
    expect(idsFor("patient.read_360", "session.read", "media.read")).toHaveLength(6);
  });

  it("a_role_without_patient_360_sees_no_tab", () => {
    expect(idsFor()).toEqual([]);
  });

  it("every_tab_has_a_short_label_for_the_phone", () => {
    expect(
      visiblePatientTabs(holding("patient.read_360", "session.read", "media.read")).every(
        (tab) => tab.shortLabel !== undefined,
      ),
    ).toBe(true);
  });
});
