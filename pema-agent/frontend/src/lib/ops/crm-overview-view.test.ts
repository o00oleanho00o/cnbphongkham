import { describe, expect, it } from "vitest";

import {
  countsOf,
  defaultSegment,
  expectedVisitText,
  filterActivities,
  formatDay,
  SEGMENT_ORDER,
  type Activity,
} from "./crm-overview-view";

const activity = (
  id: string,
  channel: Activity["channel"],
  outcome: Activity["outcome"],
): Activity => ({
  id,
  patient_id: "p",
  task_id: null,
  kind: "cskh",
  channel,
  outcome,
  note: "ghi chú mẫu",
  actor_user_id: null,
  occurred_at: "2026-09-20T09:00:00+07:00",
});

describe("expectedVisitText", () => {
  it("says_how_many_days_a_visit_is_overdue", () => {
    expect(expectedVisitText({ overdue_days: 14, expected_next_visit_at: "2026-09-06" })).toBe(
      "Quá hạn 14 ngày",
    );
  });

  it("gives_the_expected_day_when_nothing_is_overdue", () => {
    expect(expectedVisitText({ overdue_days: 0, expected_next_visit_at: "2026-10-05" })).toBe(
      "Dự kiến 05/10/2026",
    );
  });

  it("says_so_when_the_doctor_has_set_no_day", () => {
    expect(expectedVisitText({ overdue_days: 0, expected_next_visit_at: null })).toBe(
      "Chưa có ngày dự kiến",
    );
  });
});

describe("formatDay", () => {
  it("writes_a_date_the_vietnamese_way", () => {
    expect(formatDay("2026-09-20")).toBe("20/09/2026");
    expect(formatDay("2026-09-20T09:00:00+07:00")).toBe("20/09/2026");
  });

  it("shows_text_that_is_not_a_date_as_it_came", () => {
    expect(formatDay("sắp tới")).toBe("sắp tới");
  });
});

describe("countsOf and defaultSegment", () => {
  it("counts_a_group_the_answer_lacks_as_zero", () => {
    const counts = countsOf([{ key: "treating", count: 3 }]);
    expect(counts.treating).toBe(3);
    expect(counts.dormant).toBe(0);
    expect(Object.keys(counts)).toEqual([...SEGMENT_ORDER]);
  });

  it("opens_on_the_first_stage_that_has_patients", () => {
    expect(defaultSegment(countsOf([{ key: "treating", count: 3 }]))).toBe("treating");
  });

  it("opens_on_the_first_card_when_every_group_is_empty", () => {
    expect(defaultSegment(countsOf([]))).toBe("new");
  });

  it("does_not_open_on_the_at_risk_cut_while_a_stage_has_patients", () => {
    expect(
      defaultSegment(
        countsOf([
          { key: "at_risk", count: 2 },
          { key: "dormant", count: 1 },
        ]),
      ),
    ).toBe("dormant");
  });
});

describe("filterActivities", () => {
  const items = [
    activity("1", "call", "no_need"),
    activity("2", "zalo", "unanswered"),
    activity("3", "zalo", "booked"),
  ];

  it("keeps_every_row_without_a_filter", () => {
    expect(filterActivities(items, { channel: "all", outcome: "all" })).toHaveLength(3);
  });

  it("narrows_by_channel", () => {
    expect(filterActivities(items, { channel: "zalo", outcome: "all" }).map((a) => a.id)).toEqual([
      "2",
      "3",
    ]);
  });

  it("narrows_by_channel_and_outcome_together", () => {
    expect(
      filterActivities(items, { channel: "zalo", outcome: "booked" }).map((a) => a.id),
    ).toEqual(["3"]);
  });
});
