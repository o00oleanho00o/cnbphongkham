import { describe, expect, it } from "vitest";

import {
  ageLabel,
  filterReception,
  matchesStatus,
  pageCount,
  pageOf,
  receptionActions,
  receptionCounts,
} from "./reception-view";
import type { ScheduleItem } from "./schedule-view";

function visit(over: Partial<ScheduleItem>): ScheduleItem {
  return {
    id: "a-1",
    patient_id: "p-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    doctor_id: "d-an",
    doctor_name: "BS. An",
    starts_at: "2026-09-20T09:00:00+07:00",
    duration_min: 30,
    status: "booked",
    version: 1,
    ...over,
  };
}

const none = () => "";

describe("reception counts", () => {
  const items = [
    visit({ id: "1", status: "booked" }),
    visit({ id: "2", status: "confirmed" }),
    visit({ id: "3", status: "arrived" }),
    visit({ id: "4", status: "in_progress" }),
    visit({ id: "5", status: "completed" }),
    visit({ id: "6", status: "missed" }),
    visit({ id: "7", status: "cancelled" }),
  ];

  it("counts_the_not_yet_arrived_tile_as_booked_plus_confirmed_like_the_old_tile", () => {
    expect(receptionCounts(items).byTile.pending).toBe(2);
  });

  it("counts_arrived_in_progress_and_completed_as_came", () => {
    const counts = receptionCounts(items);
    expect(counts.total).toBe(7);
    expect(counts.came).toBe(3);
  });

  it("matches_a_status_against_all_pending_or_itself", () => {
    expect(matchesStatus("confirmed", "pending")).toBe(true);
    expect(matchesStatus("arrived", "pending")).toBe(false);
    expect(matchesStatus("arrived", "all")).toBe(true);
    expect(matchesStatus("arrived", "arrived")).toBe(true);
  });
});

describe("reception filters", () => {
  const items = [
    visit({ id: "late", starts_at: "2026-09-20T15:00:00+07:00", patient_name: "Lê Hoàng Yến" }),
    visit({
      id: "early",
      starts_at: "2026-09-20T08:00:00+07:00",
      patient_code: "P002",
      doctor_id: "d-tam",
    }),
  ];

  it("sorts_by_start_time", () => {
    const rows = filterReception(items, { status: "all", doctorId: "", query: "" }, none);
    expect(rows.map((r) => r.id)).toEqual(["early", "late"]);
  });

  it("filters_by_doctor", () => {
    const rows = filterReception(items, { status: "all", doctorId: "d-tam", query: "" }, none);
    expect(rows.map((r) => r.id)).toEqual(["early"]);
  });

  it("searches_name_code_and_phone_ignoring_case", () => {
    const phone = (item: ScheduleItem) => (item.id === "late" ? "0900 111 222" : "");
    const by = (query: string) =>
      filterReception(items, { status: "all", doctorId: "", query }, phone).map((r) => r.id);
    expect(by("YẾN")).toEqual(["late"]);
    expect(by("p002")).toEqual(["early"]);
    expect(by("111 222")).toEqual(["late"]);
    expect(by("zzz")).toEqual([]);
  });
});

describe("paging of 25", () => {
  const rows = Array.from({ length: 31 }, (_, i) => i);

  it("has_two_pages_for_31_rows_and_one_for_none", () => {
    expect(pageCount(31)).toBe(2);
    expect(pageCount(25)).toBe(1);
    expect(pageCount(0)).toBe(1);
  });

  it("slices_25_then_the_rest_and_clamps_a_page_out_of_range", () => {
    expect(pageOf(rows, 1)).toHaveLength(25);
    expect(pageOf(rows, 2)).toEqual([25, 26, 27, 28, 29, 30]);
    expect(pageOf(rows, 9)).toHaveLength(6);
    expect(pageOf(rows, 0)).toHaveLength(25);
  });
});

describe("what a row offers", () => {
  const all = () => true;
  const nothing = () => false;

  it("offers_check_in_and_absent_for_booked_and_confirmed", () => {
    expect(receptionActions("booked", all)).toEqual(["check-in", "miss"]);
    expect(receptionActions("confirmed", all)).toEqual(["check-in", "miss"]);
  });

  it("offers_invite_in_for_a_waiting_patient", () => {
    expect(receptionActions("arrived", all)).toEqual(["start"]);
  });

  it("offers_nothing_for_the_other_statuses_and_for_a_role_without_check_in", () => {
    (["in_progress", "completed", "cancelled", "missed"] as const).forEach((status) =>
      expect(receptionActions(status, all)).toEqual([]),
    );
    expect(receptionActions("booked", nothing)).toEqual([]);
  });
});

describe("age label", () => {
  it("counts_full_years_and_is_empty_without_a_birth_date", () => {
    expect(ageLabel("1994-09-21", "2026-09-20")).toBe("31 tuổi");
    expect(ageLabel("1994-09-20", "2026-09-20")).toBe("32 tuổi");
    expect(ageLabel(null, "2026-09-20")).toBe("");
    expect(ageLabel("not-a-date", "2026-09-20")).toBe("");
  });
});
