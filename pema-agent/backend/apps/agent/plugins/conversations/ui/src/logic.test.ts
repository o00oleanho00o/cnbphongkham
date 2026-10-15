import { describe, expect, it } from "vitest";

import { tickedOne, tickedAll } from "./logic";

describe("ticking conversations to delete", () => {
  it("ticks_and_unticks_one_without_changing_the_list_it_was_given", () => {
    const before = ["a"];

    expect(tickedOne(before, "b")).toEqual(["a", "b"]);
    expect(tickedOne(["a", "b"], "a")).toEqual(["b"]);
    expect(before).toEqual(["a"]);
  });

  it("ignores_a_tick_past_the_limit_but_still_allows_unticking", () => {
    expect(tickedOne(["a", "b"], "c", 2)).toEqual(["a", "b"]);
    expect(tickedOne(["a", "b"], "b", 2)).toEqual(["a"]);
  });

  it("ticks_the_first_ids_shown_up_to_the_limit_and_clears_when_all_are_ticked", () => {
    expect(tickedAll([], ["a", "b", "c"], 2)).toEqual(["a", "b"]);
    expect(tickedAll(["a"], ["a", "b"])).toEqual(["a", "b"]);
    expect(tickedAll(["a", "b"], ["a", "b"])).toEqual([]);
    expect(tickedAll([], [])).toEqual([]);
  });
});
