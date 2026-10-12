import { describe, expect, it } from "vitest";

import {
  audienceChangeNeedsAsk,
  canExpire,
  canRestore,
  collapsedText,
  eventLabel,
  indentOf,
  internalSections,
  isDirty,
  kindLabel,
  pageCountOf,
  periodError,
  sameList,
  sizeWarning,
  splitError,
  statusOf,
  toggled,
} from "./detail-logic";

describe("sizeWarning", () => {
  it("warns_under_150_and_over_1500_only", () => {
    expect(sizeWarning(149)).toContain("ngắn");
    expect(sizeWarning(150)).toBeNull();
    expect(sizeWarning(1500)).toBeNull();
    expect(sizeWarning(1501)).toContain("dài");
  });
});

describe("collapsedText", () => {
  it("keeps_short_text_and_cuts_long_text", () => {
    expect(collapsedText("ngắn")).toBe("ngắn");
    const cut = collapsedText("a".repeat(900));
    expect(cut.length).toBeLessThan(900);
    expect(cut.endsWith("...")).toBe(true);
  });
});

describe("labels", () => {
  it("names_known_kinds_and_events_and_passes_unknown_ones_through", () => {
    expect(kindLabel("internal_script")).toBe("Kịch bản nội bộ");
    expect(kindLabel("other")).toBe("other");
    expect(eventLabel("reindexed")).toBe("Nạp lại");
    expect(eventLabel("zzz")).toBe("zzz");
  });

  it("restores_only_from_edited_or_replaced", () => {
    const event = (kind: string) => ({ id: "e", at: "", kind, by: "", note: "" });
    expect(canRestore(event("edited"))).toBe(true);
    expect(canRestore(event("replaced"))).toBe(true);
    expect(canRestore(event("approved"))).toBe(false);
  });
});

describe("internalSections", () => {
  it("finds_headings_that_read_like_staff_material_ignoring_accents", () => {
    const outline = [
      { level: 2, title: "Bảng giá", chunks: 1, chars: 10 },
      { level: 2, title: "Kịch bản chốt sale", chunks: 1, chars: 10 },
      { level: 3, title: "Hoa hồng tư vấn", chunks: 1, chars: 10 },
    ];
    expect(internalSections(outline)).toEqual(["Kịch bản chốt sale", "Hoa hồng tư vấn"]);
  });
});

describe("selection helpers", () => {
  it("toggles_without_changing_the_input", () => {
    const before = [1, 2];
    expect(toggled(before, 3)).toEqual([1, 2, 3]);
    expect(toggled(before, 1)).toEqual([2]);
    expect(before).toEqual([1, 2]);
    expect(toggled(["NAM"], "HORI")).toEqual(["NAM", "HORI"]);
  });

  it("compares_lists_ignoring_order", () => {
    expect(sameList(["a", "b"], ["b", "a"])).toBe(true);
    expect(sameList(["a"], ["a", "b"])).toBe(false);
  });
});

describe("forms", () => {
  it("sees_unsaved_text_only_when_it_differs", () => {
    expect(isDirty(null, "x")).toBe(false);
    expect(isDirty("x", "x")).toBe(false);
    expect(isDirty("y", "x")).toBe(true);
  });

  it("rejects_a_period_that_ends_before_it_starts", () => {
    expect(periodError("2026-10-02", "2026-10-01")).not.toBeNull();
    expect(periodError("2026-10-01", "")).toBeNull();
    expect(periodError("2026-10-01", "2026-10-01")).toBeNull();
  });

  it("asks_for_a_section_and_a_title_before_splitting", () => {
    expect(splitError("Mới", [])).toContain("mục");
    expect(splitError("  ", [1])).toContain("tên");
    expect(splitError("Mới", [1])).toBeNull();
  });

  it("asks_only_when_a_source_becomes_patient_facing", () => {
    expect(audienceChangeNeedsAsk("staff", "patient")).toBe(true);
    expect(audienceChangeNeedsAsk("patient", "staff")).toBe(false);
    expect(audienceChangeNeedsAsk("patient", "patient")).toBe(false);
  });

  it("expires_only_sources_in_use_or_draft", () => {
    expect(canExpire({ lifecycle: "active" })).toBe(true);
    expect(canExpire({ lifecycle: "expired" })).toBe(false);
  });
});

describe("misc", () => {
  it("counts_pages_with_a_minimum_of_one", () => {
    expect(pageCountOf(0, 20)).toBe(1);
    expect(pageCountOf(41, 20)).toBe(3);
  });

  it("indents_by_level_with_a_cap", () => {
    expect(indentOf(1)).toBe(0);
    expect(indentOf(3)).toBe(2);
    expect(indentOf(9)).toBe(5);
  });

  it("reads_a_status_from_an_error_when_there_is_one", () => {
    expect(statusOf(Object.assign(new Error("x"), { status: 404 }))).toBe(404);
    expect(statusOf(new Error("x"))).toBeNull();
    expect(statusOf("x")).toBeNull();
  });
});
