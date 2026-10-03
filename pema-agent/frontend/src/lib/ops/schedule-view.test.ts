import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";

import {
  STATUS_ORDER,
  addDays,
  allowedActions,
  clockOf,
  dayLabel,
  dayOf,
  groupByDay,
  groupByDoctor,
  isActive,
  isDayKey,
  isEditable,
  quickAction,
  summarize,
  timeRange,
  toStartsAt,
  type ScheduleItem,
} from "./schedule-view";

const everything = () => true;
const nothing = () => false;
const checkInOnly = (permission: string) => permission === "appointment.check_in";

function item(over: Partial<ScheduleItem> = {}): ScheduleItem {
  return {
    id: "a1",
    patient_id: "p1",
    patient_code: "P001",
    doctor_id: "d1",
    starts_at: "2026-09-20T09:00:00+07:00",
    duration_min: 30,
    status: "booked",
    note: null,
    version: 1,
    patient_name: "Nguyễn Thu Hà",
    doctor_name: "BS. Tâm",
    ...over,
  };
}

describe("reception status flow", () => {
  it("offers_the_old_reception_steps_from_each_status", () => {
    expect(allowedActions("booked", everything)).toEqual(["confirm", "check-in", "miss", "cancel"]);
    expect(allowedActions("confirmed", everything)).toEqual(["check-in", "miss", "cancel"]);
    expect(allowedActions("arrived", everything)).toEqual(["start", "cancel"]);
    expect(allowedActions("in_progress", everything)).toEqual(["complete"]);
    expect(allowedActions("completed", everything)).toEqual([]);
    expect(allowedActions("cancelled", everything)).toEqual([]);
    expect(allowedActions("missed", everything)).toEqual([]);
  });

  it("offers_nothing_to_a_role_without_the_permission", () => {
    expect(allowedActions("booked", nothing)).toEqual([]);
  });

  it("splits_confirm_and_cancel_from_the_reception_steps_by_permission", () => {
    expect(allowedActions("booked", checkInOnly)).toEqual(["check-in", "miss"]);
    expect(allowedActions("booked", (p) => p === "appointment.write")).toEqual([
      "confirm",
      "cancel",
    ]);
  });

  it("puts_one_quick_button_on_the_card_for_the_next_step_of_the_visit", () => {
    expect(quickAction("booked", everything)).toBe("check-in");
    expect(quickAction("confirmed", everything)).toBe("check-in");
    expect(quickAction("arrived", everything)).toBe("start");
    expect(quickAction("in_progress", everything)).toBe("complete");
    expect(quickAction("completed", everything)).toBeNull();
    expect(quickAction("booked", nothing)).toBeNull();
  });

  it("lets_only_a_booked_or_confirmed_visit_be_moved", () => {
    expect(STATUS_ORDER.filter(isEditable)).toEqual(["booked", "confirmed"]);
  });

  it("treats_cancelled_and_missed_as_freed_slots", () => {
    expect(STATUS_ORDER.filter((s) => !isActive(s))).toEqual(["missed", "cancelled"]);
  });
});

describe("dates of the board", () => {
  it("adds_days_across_month_and_year_ends_without_a_zone", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDays("2028-03-01", -1)).toBe("2028-02-29");
  });

  it("accepts_only_real_calendar_days", () => {
    expect(isDayKey("2026-09-20")).toBe(true);
    expect(isDayKey("2026-02-30")).toBe(false);
    expect(isDayKey("20/09/2026")).toBe(false);
    expect(isDayKey("")).toBe(false);
  });

  it("reads_day_and_clock_from_the_clinic_time_string", () => {
    expect(dayOf("2026-09-20T09:30:00+07:00")).toBe("2026-09-20");
    expect(clockOf("2026-09-20T09:30:00+07:00")).toBe("09:30");
    expect(toStartsAt("2026-09-20", "09:30")).toBe("2026-09-20T09:30:00+07:00");
  });

  it("writes_the_time_range_of_a_visit", () => {
    expect(timeRange("2026-09-20T08:30:00+07:00", 45)).toBe("08:30–09:15");
    expect(timeRange("2026-09-20T11:45:00+07:00", 30)).toBe("11:45–12:15");
  });

  it("labels_a_day_with_its_weekday", () => {
    expect(dayLabel("2026-09-20")).toBe("CN 20/09");
    expect(dayLabel("2026-09-21")).toBe("T2 21/09");
  });
});

describe("grouping", () => {
  it("groups_a_week_by_day_and_keeps_empty_days", () => {
    const rows = [item({ id: "a" }), item({ id: "b", starts_at: "2026-09-22T10:00:00+07:00" })];
    const week = groupByDay(rows, "2026-09-20", 7);

    expect(week.map((d) => d.day)).toEqual([
      "2026-09-20",
      "2026-09-21",
      "2026-09-22",
      "2026-09-23",
      "2026-09-24",
      "2026-09-25",
      "2026-09-26",
    ]);
    expect(week.map((d) => d.items.length)).toEqual([1, 0, 1, 0, 0, 0, 0]);
  });

  it("makes_a_column_per_doctor_and_one_for_visits_without_a_doctor", () => {
    const doctors: Schemas["ScheduleDoctor"][] = [
      { id: "d1", name: "BS. An" },
      { id: "d2", name: "BS. Mai" },
    ];
    const rows = [
      item({ id: "a", doctor_id: "d2" }),
      item({ id: "b", doctor_id: null }),
      item({ id: "c", doctor_id: "d1" }),
    ];
    const columns = groupByDoctor(rows, doctors);

    expect(columns.map((c) => [c.name, c.items.map((i) => i.id)])).toEqual([
      ["BS. An", ["c"]],
      ["BS. Mai", ["a"]],
      ["Chưa gán bác sĩ", ["b"]],
    ]);
  });

  it("adds_no_loose_column_when_every_visit_has_a_doctor", () => {
    const columns = groupByDoctor([item()], [{ id: "d1", name: "BS. An" }]);

    expect(columns.map((c) => c.name)).toEqual(["BS. An"]);
  });
});

describe("summary tiles", () => {
  it("counts_active_visits_and_treatment_minutes_without_cancelled_or_missed", () => {
    const rows = [
      item({ id: "1", duration_min: 30 }),
      item({ id: "2", status: "arrived", duration_min: 45 }),
      item({ id: "3", status: "cancelled", duration_min: 60 }),
      item({ id: "4", status: "missed", duration_min: 15 }),
    ];
    const summary = summarize(rows);

    expect(summary.total).toBe(2);
    expect(summary.treatmentMin).toBe(75);
    expect(summary.waiting).toBe(1);
    expect(summary.closed).toBe(2);
    expect(summary.byStatus.booked).toBe(1);
  });

  it("is_all_zero_for_an_empty_day", () => {
    expect(summarize([])).toMatchObject({ total: 0, treatmentMin: 0, waiting: 0, closed: 0 });
  });
});
