import { describe, expect, it } from "vitest";

import { RANGES, RANGE_LABEL, barWidth, percentLabel, spanLabel } from "./dashboard-view";

describe("dashboard wording", () => {
  it("shows_a_dash_not_zero_percent_when_the_backend_had_nothing_to_divide", () => {
    expect(percentLabel(null)).toBe("–");
    expect(percentLabel(undefined)).toBe("–");
    expect(percentLabel(0)).toBe("0%");
    expect(percentLabel(67)).toBe("67%");
  });

  it("names_the_three_ranges_in_the_old_words", () => {
    expect(RANGES.map((r) => RANGE_LABEL[r])).toEqual(["Hôm nay", "Tuần này", "Tháng này"]);
  });

  it("writes_a_day_and_a_span", () => {
    expect(spanLabel("2026-09-20", "2026-09-20")).toBe("20/09/2026");
    expect(spanLabel("2026-09-14", "2026-09-20")).toBe("14/09 – 20/09/2026");
  });

  it("sizes_a_bar_by_its_share_and_never_hides_a_small_non_zero_value", () => {
    expect(barWidth(0, 10)).toBe("0%");
    expect(barWidth(5, 0)).toBe("0%");
    expect(barWidth(5, 10)).toBe("50%");
    expect(barWidth(1, 1000)).toBe("3%");
  });
});
