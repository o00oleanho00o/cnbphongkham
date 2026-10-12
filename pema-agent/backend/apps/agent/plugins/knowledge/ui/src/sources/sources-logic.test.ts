import { describe, expect, it } from "vitest";

import type { Source, SourceList } from "../types";
import {
  NO_FILTERS,
  allSelected,
  bulkActionOf,
  bulkDoneText,
  deleteText,
  failureLines,
  hasFilters,
  kindText,
  needsRefresh,
  pageCount,
  pruneSelection,
  rangeText,
  toQuery,
  toggleAll,
  toggleId,
  visibleWarnings,
} from "./sources-logic";

function source(partial: Partial<Source> = {}): Source {
  return {
    id: "s1",
    title: "Bảng giá",
    doc_code: null,
    kind: "file",
    format: "md",
    size: 100,
    services: [],
    audience: "patient",
    processing: "ready",
    progress: { chunks: 4, labelled: 4, embedded: 0 },
    error: null,
    lifecycle: "active",
    version: null,
    effective_from: null,
    effective_to: null,
    approved: true,
    approved_by: "Quản trị",
    approved_at: null,
    chunk_count: 4,
    note: "",
    created_by: "Quản trị",
    created_at: "",
    updated_at: "",
    ...partial,
  };
}

function list(items: Source[], processing = 0): SourceList {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 30,
    warnings: [],
    summary: { ready: 0, chunks: 0, embedded_percent: 0, errors: 0, unapproved: 0, processing },
  };
}

describe("toQuery", () => {
  it("drops_empty_filters_and_page_one", () => {
    expect(toQuery(NO_FILTERS, 1)).toEqual({
      q: undefined,
      processing: undefined,
      audience: undefined,
      service: undefined,
      lifecycle: undefined,
      approved: undefined,
      page: undefined,
    });
  });

  it("maps_the_unapproved_button_to_approved_false", () => {
    const query = toQuery({ ...NO_FILTERS, q: "  giá ", unapproved: true, audience: "staff" }, 3);
    expect(query).toMatchObject({ q: "giá", approved: false, audience: "staff", page: 3 });
  });
});

describe("hasFilters", () => {
  it("is_false_for_none_and_true_for_any", () => {
    expect(hasFilters(NO_FILTERS)).toBe(false);
    expect(hasFilters({ ...NO_FILTERS, unapproved: true })).toBe(true);
    expect(hasFilters({ ...NO_FILTERS, service: "NAM" })).toBe(true);
  });
});

describe("needsRefresh", () => {
  it("is_false_without_a_list_or_when_all_are_done", () => {
    expect(needsRefresh(null)).toBe(false);
    expect(needsRefresh(list([source()]))).toBe(false);
  });

  it("is_true_when_a_row_is_queued_or_processing", () => {
    expect(needsRefresh(list([source({ processing: "queued" })]))).toBe(true);
    expect(needsRefresh(list([source({ processing: "processing" })]))).toBe(true);
  });

  it("is_true_when_the_summary_counts_work_on_another_page", () => {
    expect(needsRefresh(list([source()], 2))).toBe(true);
  });
});

describe("paging", () => {
  it("counts_pages_and_never_less_than_one", () => {
    expect(pageCount(0, 30)).toBe(1);
    expect(pageCount(30, 30)).toBe(1);
    expect(pageCount(31, 30)).toBe(2);
  });

  it("writes_the_range", () => {
    expect(rangeText({ total: 64, page: 2, page_size: 30 }, 30)).toBe("31-60 / 64 nguồn");
    expect(rangeText({ total: 0, page: 1, page_size: 30 }, 0)).toBe("0 nguồn");
  });
});

describe("selection", () => {
  it("toggles_one_id", () => {
    expect(toggleId(["a"], "b")).toEqual(["a", "b"]);
    expect(toggleId(["a", "b"], "a")).toEqual(["b"]);
  });

  it("select_all_adds_the_missing_and_a_second_press_clears_the_page", () => {
    const page = ["a", "b", "c"];
    expect(toggleAll(["a", "x"], page)).toEqual(["a", "x", "b", "c"]);
    expect(allSelected(["a", "b", "c"], page)).toBe(true);
    expect(toggleAll(["a", "b", "c", "x"], page)).toEqual(["x"]);
    expect(allSelected([], [])).toBe(false);
  });

  it("prune_keeps_only_ids_on_screen", () => {
    expect(pruneSelection(["a", "z"], ["a", "b"])).toEqual(["a"]);
  });
});

describe("words", () => {
  it("names_kind_and_format", () => {
    expect(kindText({ kind: "file", format: "pdf" })).toEqual({ kind: "Tệp", format: "PDF" });
    expect(kindText({ kind: "text", format: "text" }).kind).toBe("Văn bản gõ tay");
  });

  it("hides_the_unapproved_warning_only", () => {
    expect(visibleWarnings(["Embedding chưa kết nối", "3 nguồn chưa duyệt", "1 nguồn lỗi"])).toEqual([
      "Embedding chưa kết nối",
      "1 nguồn lỗi",
    ]);
  });

  it("delete_text_counts_chunks_and_says_the_agent_stops_citing", () => {
    const text = deleteText([source({ chunk_count: 13 }), source({ id: "s2", chunk_count: 8 })]);
    expect(text).toContain("2 nguồn");
    expect(text).toContain("21 đoạn");
    expect(text).toContain("không còn dẫn chứng");
  });

  it("writes_the_done_sentence", () => {
    expect(bulkDoneText("approve", 3)).toBe("Đã duyệt 3 nguồn");
    expect(bulkDoneText("audience-staff", 1)).toBe("Đã đặt đối tượng Nội bộ cho 1 nguồn");
  });

  it("maps_a_bulk_kind_to_the_request", () => {
    expect(bulkActionOf("audience-staff")).toEqual({ action: "audience", audience: "staff" });
    expect(bulkActionOf("delete")).toEqual({ action: "delete" });
  });

  it("failure_lines_use_the_title_or_the_id", () => {
    const lines = failureLines(
      { done: 0, failed: [{ id: "s1", message: "Đang lỗi" }, { id: "gone", message: "Không thấy" }] },
      [source()],
    );
    expect(lines).toEqual(["Bảng giá: Đang lỗi", "gone: Không thấy"]);
  });
});
