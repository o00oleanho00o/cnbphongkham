import { describe, expect, it } from "vitest";

import type { EmbeddingSettings, KnowledgeSettings } from "../types";
import {
  RANGES,
  embeddingChange,
  embeddingFormOf,
  embeddingProblems,
  embeddingTestText,
  keyEditOf,
  keyToSend,
  asLevel,
  jevNotice,
  judgingChange,
  numberProblem,
  parserChange,
  parserProblems,
  reembedWarning,
  searchChange,
  searchFormOf,
  searchProblems,
  urlProblem,
} from "./settings-logic";

const EMBEDDING: EmbeddingSettings = {
  base_url: "https://embed.example.test/v1",
  model: "demo-embedding",
  dimensions: 1024,
  query_prefix: "",
  document_prefix: "",
  has_key: true,
  origin: "saved",
  chunks_without_vector: 3,
};

const SEARCH: KnowledgeSettings["search"] = {
  results: 8,
  min_score: 0.2,
  char_budget: 6000,
  patient_channel_prefix: "zalo-",
  patient_only_approved: true,
};

describe("numbers", () => {
  it("accepts_a_value_inside_its_range", () => {
    expect(numberProblem("1024", RANGES.dimensions)).toBeNull();
    expect(numberProblem("0,35", RANGES.min_score)).toBeNull();
  });

  it.each(["", "abc", "0", "16", "5000", "10.5"])("refuses_%s_as_a_number_of_dimensions", (text) => {
    expect(numberProblem(text, RANGES.dimensions)).not.toBeNull();
  });

  it("refuses_a_score_above_one", () => {
    expect(numberProblem("1.5", RANGES.min_score)).toMatch(/từ 0 đến 1/);
  });
});

describe("addresses", () => {
  it("lets_an_optional_address_stay_empty", () => {
    expect(urlProblem("", "Địa chỉ", false)).toBeNull();
    expect(urlProblem("", "Địa chỉ", true)).not.toBeNull();
  });

  it("wants_http_or_https", () => {
    expect(urlProblem("https://a.test", "Địa chỉ", true)).toBeNull();
    expect(urlProblem("ftp://a.test", "Địa chỉ", true)).not.toBeNull();
  });
});

describe("embedding", () => {
  const form = embeddingFormOf(EMBEDDING);

  it("sends_nothing_when_nothing_changed", () => {
    expect(embeddingChange(form, EMBEDDING, keyEditOf(true))).toBeNull();
  });

  it("sends_only_the_fields_that_changed_and_the_dimensions_as_a_number", () => {
    const change = embeddingChange({ ...form, model: " other ", dimensions: "768" }, EMBEDDING, keyEditOf(true));

    expect(change).toEqual({ embedding: { model: "other", dimensions: 768 } });
  });

  it("does_not_send_the_key_unless_one_was_typed", () => {
    expect(keyToSend({ mode: "saved", typed: "ignored" })).toBeUndefined();
    expect(keyToSend({ mode: "typing", typed: "  " })).toBeUndefined();
    expect(keyToSend({ mode: "typing", typed: " sk-demo " })).toBe("sk-demo");
  });

  it("sends_an_empty_key_to_remove_the_stored_one", () => {
    expect(embeddingChange(form, EMBEDDING, { mode: "removing", typed: "" })).toEqual({ embedding: { api_key: "" } });
  });

  it("flags_an_empty_model_and_a_bad_address", () => {
    const problems = embeddingProblems({ ...form, model: " ", base_url: "embed" });

    expect(problems.model).toBeDefined();
    expect(problems.base_url).toBeDefined();
    expect(problems.dimensions).toBeUndefined();
  });

  it("warns_when_the_dimensions_returned_differ_from_the_saved_ones", () => {
    const text = embeddingTestText(
      { ok: true, dimensions: 768, normalised: true, ms: 1840, message: "Kết nối tốt" },
      1024,
    );

    expect(text).toContain("768 chiều");
    expect(text).toContain("đã chuẩn hóa");
    expect(text).toContain("1840 ms");
    expect(text).toContain("khác số chiều đã lưu (1024)");
  });

  it("shows_the_error_sentence_of_a_failed_test", () => {
    const text = embeddingTestText({ ok: false, dimensions: null, normalised: null, ms: null, message: "Chưa có khóa API" }, 1024);

    expect(text).toBe("Chưa có khóa API");
  });
});

describe("re-embedding", () => {
  it("says_new_chunks_are_searched_by_keyword_until_their_vectors_exist", () => {
    const warning = reembedWarning(EMBEDDING);
    expect(warning).toContain("demo-embedding");
    expect(warning).toContain("chỉ được tìm bằng từ khóa");
    expect(warning).not.toContain("vector cũ");
  });
});

describe("parser", () => {
  it("wants_an_address_for_docling_only", () => {
    expect(parserProblems({ kind: "docling", docling_url: "" }).docling_url).toBeDefined();
    expect(parserProblems({ kind: "simple", docling_url: "" }).docling_url).toBeUndefined();
  });

  it("sends_the_changed_fields", () => {
    const saved = { kind: "simple", docling_url: "", origin: "profile" } as const;

    expect(parserChange({ kind: "docling", docling_url: " http://docling.test " }, saved)).toEqual({
      parser: { kind: "docling", docling_url: "http://docling.test" },
    });
    expect(parserChange({ kind: "simple", docling_url: "" }, saved)).toBeNull();
  });
});

describe("judging", () => {
  const saved = { enabled: false, level: "medium" } as const;

  it("sends_only_what_changed", () => {
    expect(judgingChange({ ...saved, enabled: true }, saved)).toEqual({ judging: { enabled: true } });
    expect(judgingChange({ enabled: true, level: "strict" }, saved)).toEqual({
      judging: { enabled: true, level: "strict" },
    });
    expect(judgingChange(saved, saved)).toBeNull();
  });

  it("reads_a_level_from_a_select_value_and_falls_back_to_medium", () => {
    expect(asLevel("strict")).toBe("strict");
    expect(asLevel("loose")).toBe("loose");
    expect(asLevel("nonsense")).toBe("medium");
  });

  it("says_what_is_missing_before_the_judge_can_work", () => {
    expect(jevNotice(null)).toBeNull();
    expect(jevNotice({ on: false, hasKey: false })).toContain("Plugin Jev đang tắt");
    expect(jevNotice({ on: true, hasKey: false })).toContain("Chưa có khóa TypeSafe");
    expect(jevNotice({ on: true, hasKey: true })).toBeNull();
  });
});

describe("search", () => {
  it("checks_each_number_against_its_range", () => {
    const problems = searchProblems({ ...searchFormOf(SEARCH), results: "0", char_budget: "100", min_score: "2" });

    expect(Object.entries(problems).filter(([, text]) => text).map(([key]) => key)).toEqual([
      "results",
      "min_score",
      "char_budget",
    ]);
  });

  it("sends_numbers_as_numbers", () => {
    const change = searchChange({ ...searchFormOf(SEARCH), results: "12", patient_only_approved: false }, SEARCH);

    expect(change).toEqual({ search: { results: 12, patient_only_approved: false } });
  });
});
