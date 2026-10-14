import { describe, expect, it } from "vitest";

import { capHint, formatCount, formatUsd, hasProblems, parseTokens, problems, settingsChange, todayText } from "./logic";
import type { Settings } from "./types";

const SAVED: Settings = { model: "jev-latest", daily_token_cap: 2_000_000, has_key: true, usd_per_million_tokens: 0.042 };
const FORM = { model: "jev-latest", cap: "2.000.000" };

describe("numbers", () => {
  it("writes_a_count_with_dots", () => {
    expect(formatCount(2_000_000)).toBe("2.000.000");
    expect(formatCount(950)).toBe("950");
    expect(formatCount(0)).toBe("0");
  });

  it("reads_tokens_typed_with_dots_commas_or_spaces", () => {
    expect(parseTokens("2.000.000")).toBe(2_000_000);
    expect(parseTokens("2 000 000")).toBe(2_000_000);
    expect(parseTokens(" 0 ")).toBe(0);
  });

  it("refuses_what_is_not_a_whole_number_in_range", () => {
    expect(parseTokens("")).toBeNull();
    expect(parseTokens("-5")).toBeNull();
    expect(parseTokens("1,5 triệu")).toBeNull();
    expect(parseTokens("10.000.000.001")).toBeNull();
  });

  it("shows_small_sums_with_six_decimals_and_larger_ones_with_four", () => {
    expect(formatUsd(0.000084)).toBe("$0,000084");
    expect(formatUsd(0.084)).toBe("$0,0840");
  });
});

describe("the form", () => {
  it("sends_nothing_when_nothing_changed", () => {
    expect(settingsChange(FORM, SAVED)).toBeNull();
  });

  it("sends_only_what_changed", () => {
    expect(settingsChange({ ...FORM, cap: "500000" }, SAVED)).toEqual({ daily_token_cap: 500_000 });
    expect(settingsChange({ model: " jev-1.13.0 ", cap: "2.000.000" }, SAVED)).toEqual({ model: "jev-1.13.0" });
  });

  it("sends_zero_for_no_limit", () => {
    expect(settingsChange({ ...FORM, cap: "0" }, SAVED)).toEqual({ daily_token_cap: 0 });
  });

  it("an_empty_key_is_no_problem_because_it_means_no_change", () => {
    expect(hasProblems(problems(FORM, ""))).toBe(false);
  });

  it("each_wrong_field_is_named", () => {
    expect(problems({ ...FORM, model: "Bad Model" }, "").model).toBeDefined();
    expect(problems({ ...FORM, cap: "abc" }, "").cap).toBeDefined();
    expect(problems(FORM, "short").key).toBeDefined();
    expect(problems(FORM, "a-long-enough-key").key).toBeUndefined();
  });
});

describe("words", () => {
  it("says_how_far_the_day_has_gone", () => {
    expect(todayText(120_000, 2_000_000)).toBe("Hôm nay 120.000 / 2.000.000 token (6%)");
    expect(todayText(3_000_000, 2_000_000)).toBe("Hôm nay 3.000.000 / 2.000.000 token (100%)");
    expect(todayText(5, 0)).toBe("Hôm nay 5 token (không giới hạn)");
  });

  it("says_what_the_whole_allowance_would_cost", () => {
    expect(capHint(2_000_000, 0.042)).toContain("$0,0840");
    expect(capHint(0, 0.042)).toContain("Không giới hạn");
    expect(capHint(null, 0.042)).toContain("mỗi ngày");
  });
});
