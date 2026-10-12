import { describe, expect, it } from "vitest";

import type { ConfirmItem, PreviewItem } from "../types";
import {
  audienceDefaults,
  base64FromDataUrl,
  batchBySize,
  defaultDraft,
  groupByCode,
  ignoredText,
  patientRisks,
  planFolder,
  refusalOf,
  splitByPreview,
  summarise,
  summaryText,
  toConfirmItems,
  validateFile,
  validateText,
} from "./add-logic";
import { emptyMeta } from "./frontmatter";

function item(partial: Partial<PreviewItem> & { key: string }): PreviewItem {
  return {
    name: `${partial.key}.md`,
    format: "md",
    size: 100,
    meta: emptyMeta(),
    outline: [],
    chunk_count: 5,
    avg_chars: 300,
    tables_split: 0,
    warnings: [],
    same_code_as: null,
    same_content_as: null,
    error: null,
    ...partial,
  };
}

function entry(source: PreviewItem, draft: Partial<ReturnType<typeof defaultDraft>> = {}) {
  return { item: source, draft: { ...defaultDraft(source, "2026-10-12"), ...draft } };
}

describe("validateFile", () => {
  it("accepts_the_allowed_types", () => {
    expect(validateFile({ name: "A.MD", size: 10 })).toBeNull();
    expect(validateFile({ name: "b.pdf", size: 10 })).toBeNull();
  });
  it("flags_a_wrong_type_with_its_extension", () => {
    expect(validateFile({ name: "a.zip", size: 10 })).toContain(".zip");
  });
  it("flags_a_file_over_25_mb_and_an_empty_one", () => {
    expect(validateFile({ name: "a.pdf", size: 26 * 1024 * 1024 })).toContain("tối đa");
    expect(validateFile({ name: "a.pdf", size: 0 })).toBe("Tệp rỗng.");
  });
});

describe("validateText", () => {
  it("needs_a_title_and_content", () => {
    expect(validateText("", "x")).toBe("Nhập tiêu đề.");
    expect(validateText("t", " ")).toBe("Nhập nội dung.");
    expect(validateText("t", "x")).toBeNull();
  });
  it("stops_at_100000_characters", () => {
    expect(validateText("t", "x".repeat(100_000))).toBeNull();
    expect(validateText("t", "x".repeat(100_001))).toContain("tối đa");
  });
});

describe("planFolder", () => {
  const files = [
    { name: "a.md", size: 10 },
    { name: "b.png", size: 10 },
    { name: ".hidden.md", size: 10 },
    { name: "c.pdf", size: 30 * 1024 * 1024 },
  ];
  it("keeps_allowed_files_and_counts_the_rest", () => {
    const plan = planFolder(files);
    expect(plan.accepted.map((file) => file.name)).toEqual(["a.md"]);
    expect(plan.ignoredType).toBe(2);
    expect(plan.rejected.map((rejection) => rejection.name)).toEqual(["c.pdf"]);
  });
  it("caps_at_200_files", () => {
    const many = Array.from({ length: 230 }, (_, index) => ({ name: `f${index}.md`, size: 5 }));
    const plan = planFolder(many);
    expect(plan.accepted).toHaveLength(200);
    expect(plan.ignoredOverCap).toBe(30);
    expect(ignoredText(plan)).toBe("Bỏ qua 30 tệp vượt giới hạn 200 tệp.");
  });
  it("says_nothing_when_nothing_is_ignored", () => {
    expect(ignoredText({ ignoredType: 0, ignoredOverCap: 0 })).toBe("");
  });
});

describe("batchBySize", () => {
  it("groups_by_count", () => {
    expect(batchBySize([1, 2, 3, 4, 5], () => 1, 2, 100)).toEqual([[1, 2], [3, 4], [5]]);
  });
  it("starts_a_new_group_when_the_bytes_would_pass_the_limit", () => {
    expect(batchBySize(["a", "b", "c"], () => 6, 10, 10)).toEqual([["a"], ["b"], ["c"]]);
  });
  it("sends_one_heavy_item_alone", () => {
    expect(batchBySize([1, 50, 1], (n) => n, 10, 10)).toEqual([[1], [50], [1]]);
  });
  it("gives_nothing_for_nothing", () => {
    expect(batchBySize([], () => 1)).toEqual([]);
  });
});

describe("base64FromDataUrl", () => {
  it("keeps_only_the_data", () => {
    expect(base64FromDataUrl("data:application/pdf;base64,QUJD")).toBe("QUJD");
    expect(base64FromDataUrl("nothing")).toBe("");
  });
});

describe("defaults", () => {
  it("patient_head_means_patient_and_approved", () => {
    expect(audienceDefaults("patient")).toEqual({ audience: "patient", approved: true });
  });
  it("staff_head_means_internal_and_approved", () => {
    expect(audienceDefaults("staff")).toEqual({ audience: "staff", approved: true });
  });
  it("no_head_means_internal_and_not_approved", () => {
    expect(audienceDefaults(null)).toEqual({ audience: "staff", approved: false });
  });
  it("takes_title_dates_and_code_from_the_head", () => {
    const draft = defaultDraft(
      item({
        key: "k",
        name: "D07.md",
        meta: { ...emptyMeta(), title: "Giá", doc_code: "D07", effective_from: "2026-10-01", audience: "patient", version: "2.0" },
      }),
      "2026-10-12",
    );
    expect(draft).toMatchObject({ title: "Giá", docCode: "D07", from: "2026-10-01", to: "", audience: "patient", approved: true, version: "2.0" });
  });
  it("falls_back_to_the_file_name_and_today", () => {
    expect(defaultDraft(item({ key: "k", name: "faq.txt" }), "2026-10-12")).toMatchObject({ title: "faq", from: "2026-10-12", approved: false });
  });
  it("skips_a_file_with_the_same_content_by_default", () => {
    expect(defaultDraft(item({ key: "k", same_content_as: { id: "s", title: "T" } })).action).toBe("skip");
  });
});

describe("refusalOf", () => {
  it("refuses_a_challenge_file_unless_benchmark_is_on", () => {
    const challenge = item({ key: "k", meta: { ...emptyMeta(), ingest_role: "challenge" } });
    expect(refusalOf(challenge, false)).toContain("benchmark");
    expect(refusalOf(challenge, true)).toBeNull();
  });
  it("refuses_a_file_that_could_not_be_read", () => {
    expect(refusalOf(item({ key: "k", error: "PDF là ảnh scan" }), true)).toBe("PDF là ảnh scan");
  });
  it("refuses_a_file_of_another_clinic", () => {
    const other = item({ key: "k", warnings: [{ code: "tenant", level: "error", text: "Của phòng khám X" }] });
    expect(refusalOf(other, true)).toBe("Của phòng khám X");
  });
});

describe("patientRisks", () => {
  it("lists_internal_script_and_personal_data_only", () => {
    const risky = item({
      key: "k",
      warnings: [
        { code: "no_headings", level: "warn", text: "a" },
        { code: "internal_script", level: "warn", text: "b" },
        { code: "personal_data", level: "warn", text: "c" },
      ],
    });
    expect(patientRisks(risky).map((warning) => warning.code)).toEqual(["internal_script", "personal_data"]);
  });
});

describe("confirm items and summary", () => {
  const added = entry(
    item({
      key: "a",
      chunk_count: 10,
      warnings: [
        { code: "x", level: "warn", text: "w" },
        { code: "y", level: "info", text: "i" },
      ],
    }),
  );
  const same = item({ key: "b", chunk_count: 4, same_code_as: { id: "s", title: "T", version: null } });
  const skippedSame = entry(same, { action: "skip" });
  const skippedDup = entry(item({ key: "c", same_content_as: { id: "s", title: "T" } }));

  it("counts_only_files_to_add_and_not_info_warnings", () => {
    const summary = summarise([added, skippedSame, skippedDup]);
    expect(summary).toEqual({ sources: 1, chunks: 10, warnings: 1 });
    expect(summaryText(summary)).toBe("Sẽ nạp 1 nguồn, ~10 đoạn, 1 cảnh báo");
  });
  it("sends_a_skip_only_when_the_code_clashes", () => {
    const items = toConfirmItems([added, skippedSame, skippedDup]);
    expect(items.map((sent) => [sent.key, sent.on_same_code])).toEqual([
      ["a", "version"],
      ["b", "skip"],
    ]);
  });
  it("trims_text_and_turns_blanks_into_null", () => {
    const [first] = toConfirmItems([entry(item({ key: "t" }), { title: "  Giá  ", docCode: " ", to: "", supersedes: "" })]);
    expect(first).toMatchObject({ title: "Giá", doc_code: null, effective_to: null, supersedes: null });
  });
});

describe("groupByCode", () => {
  const coded = (key: string, code: string, from: string) => entry(item({ key }), { docCode: code, from });
  it("puts_versions_of_one_code_together_oldest_first", () => {
    const groups = groupByCode([coded("new", "D07", "2026-10-01"), coded("solo", "D08", "2026-10-01"), coded("old", "D07", "2026-01-01")]);
    expect(groups.map((group) => group.code)).toEqual(["D07", null]);
    expect(groups[0]?.entries.map((each) => each.item.key)).toEqual(["old", "new"]);
  });
});

describe("splitByPreview", () => {
  it("makes_one_confirm_per_preview_call", () => {
    const make = (key: string): ConfirmItem => toConfirmItems([entry(item({ key }))])[0] as ConfirmItem; // one entry in, one item out
    const groups = splitByPreview([make("a"), make("b"), make("c")], { a: "p1", b: "p2", c: "p1" });
    expect(groups.map((group) => [group.previewId, group.items.map((sent) => sent.key)])).toEqual([
      ["p1", ["a", "c"]],
      ["p2", ["b"]],
    ]);
  });
});
