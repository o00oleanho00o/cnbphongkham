import { describe, expect, it } from "vitest";

import type { SearchStage } from "../types";
import {
  formatMs,
  formatScore,
  isBlankQuestion,
  listsCandidates,
  scoreLabel,
  sourceIdOf,
  stageCount,
  stageSummary,
  startsOpen,
} from "./try-logic";

const stage = (patch: Partial<SearchStage>): SearchStage => ({
  id: "keyword",
  title: "Ứng viên từ khóa",
  ms: 10,
  note: "",
  skipped: false,
  candidates: [],
  ...patch,
});

describe("sourceIdOf", () => {
  it("takes_the_source_id_off_a_chunk_id", () => {
    expect(sourceIdOf("src-seed-1-c3")).toBe("src-seed-1");
    expect(sourceIdOf("src-mm1x2-4-c12")).toBe("src-mm1x2-4");
  });

  it("is_null_when_the_id_has_no_chunk_suffix", () => {
    expect(sourceIdOf("src-seed-1")).toBeNull();
    expect(sourceIdOf("-c3")).toBeNull();
    expect(sourceIdOf("")).toBeNull();
  });
});

describe("stages", () => {
  it("opens_only_the_final_stage", () => {
    expect(startsOpen("final")).toBe(true);
    expect(["understand", "keyword", "vector", "fused", "reranked"].some(startsOpen)).toBe(false);
  });

  it("lists_candidates_for_every_stage_but_the_first", () => {
    expect(listsCandidates("understand")).toBe(false);
    expect(listsCandidates("keyword")).toBe(true);
  });

  it("counts_candidates_and_says_when_a_stage_was_skipped", () => {
    expect(stageCount(stage({ skipped: true }))).toBe("bỏ qua");
    expect(stageCount(stage({}))).toBe("không có ứng viên");
    expect(stageCount(stage({ id: "understand" }))).toBe("");
    const candidate = { chunk_id: "a-c1", doc_code: null, source_title: "A", path: "A", excerpt: "x", score: 1 };
    expect(stageCount(stage({ candidates: [candidate, candidate] }))).toBe("2 ứng viên");
  });

  it("falls_back_to_a_short_phrase_when_a_skipped_stage_has_no_note", () => {
    expect(stageSummary(stage({ note: "Đã gộp" }))).toBe("Đã gộp");
    expect(stageSummary(stage({ skipped: true }))).toBe("Bỏ qua bước này");
    expect(stageSummary(stage({}))).toBe("");
  });
});

describe("formatting", () => {
  it("shows_milliseconds_then_seconds_with_a_comma", () => {
    expect(formatMs(12)).toBe("12 ms");
    expect(formatMs(999.4)).toBe("999 ms");
    expect(formatMs(1250)).toBe("1,3 s");
  });

  it("keeps_more_decimals_for_similarities_and_the_ranking_after_them", () => {
    expect(formatScore("keyword", 4.5)).toBe("4,50");
    expect(formatScore("vector", 0.31)).toBe("0,310");
    expect(formatScore("fused", 0.0164)).toBe("0,016");
  });

  it("names_the_number_each_stage_carries", () => {
    expect(scoreLabel("vector")).toBe("độ giống");
    expect(scoreLabel("unknown")).toBe("điểm");
  });

  it("treats_whitespace_as_no_question", () => {
    expect(isBlankQuestion("  \n ")).toBe(true);
    expect(isBlankQuestion("giá nám?")).toBe(false);
  });
});
