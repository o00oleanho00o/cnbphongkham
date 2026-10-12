import { describe, expect, it } from "vitest";

import type { Service } from "../types";
import {
  addWords,
  bodyOf,
  codeProblem,
  deleteWarning,
  formProblems,
  importRows,
  matchesQuery,
  parseServiceTable,
  removeWord,
  splitList,
  updateBody,
} from "./services-logic";

function service(partial: Partial<Service> & Pick<Service, "code">): Service {
  return {
    id: `svc-${partial.code}`,
    name: partial.code,
    aliases: [],
    description: "",
    branches: [],
    chunk_count: 0,
    enabled: true,
    ...partial,
  };
}

const NAM = service({ code: "NAM", name: "Điều trị nám", aliases: ["nám"], chunk_count: 38 });

describe("aliases", () => {
  it("splits_on_semicolons_and_commas_and_drops_empty_words", () => {
    expect(splitList(" hori; bớt hori ,, ")).toEqual(["hori", "bớt hori"]);
  });

  it("does_not_add_a_word_twice_whatever_its_letter_case", () => {
    expect(addWords(["Hori"], "hori; peel")).toEqual(["Hori", "peel"]);
  });

  it("removes_one_word", () => {
    expect(removeWord(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("codes", () => {
  it("accepts_uppercase_digits_and_underscore", () => {
    expect(codeProblem("HORI_2", [], null)).toBeNull();
  });

  it("refuses_empty_lowercase_and_accents", () => {
    expect(codeProblem("", [], null)).not.toBeNull();
    expect(codeProblem("hori", [], null)).not.toBeNull();
    expect(codeProblem("NÁM", [], null)).not.toBeNull();
  });

  it("refuses_a_code_in_use_by_another_service_but_not_by_itself", () => {
    expect(codeProblem("NAM", [NAM], null)).toMatch(/đã có/);
    expect(codeProblem("NAM", [NAM], NAM.id)).toBeNull();
  });

  it("checks_the_code_after_it_is_upper_cased", () => {
    const form = { code: " nam ", name: "x", description: "", aliases: [], branches: [], enabled: true };
    expect(formProblems(form, [NAM], null).code).toMatch(/đã có/);
    expect(bodyOf(form).code).toBe("NAM");
  });
});

describe("warnings", () => {
  it("says_how_many_chunks_a_delete_unlabels", () => {
    expect(deleteWarning(NAM)).toContain("38 đoạn");
    expect(deleteWarning(service({ code: "X" }))).toContain("Chưa có đoạn nào");
  });
});

describe("search", () => {
  it("finds_by_alias_without_accents", () => {
    expect(matchesQuery(NAM, "nam")).toBe(true);
    expect(matchesQuery(NAM, "hori")).toBe(false);
    expect(matchesQuery(NAM, "")).toBe(true);
  });
});

describe("parseServiceTable", () => {
  it("reads_a_csv_with_a_header_and_quoted_aliases", () => {
    const read = parseServiceTable('code,name,aliases,description\nhori,Bớt Hori,"hori; bớt hori",Laser\n');

    expect(read.problems).toEqual([]);
    expect(read.rows).toEqual([
      { code: "HORI", name: "Bớt Hori", aliases: ["hori", "bớt hori"], description: "Laser", branches: [], enabled: true },
    ]);
  });

  it("reads_a_markdown_table_and_skips_its_separator_line", () => {
    const text = "| Mã | Tên | Tên gọi khác | Mô tả |\n|---|---|---|---|\n| PEEL | Peel da | peel; lột da | Tẩy tế bào |";
    const read = parseServiceTable(text);

    expect(read.rows).toHaveLength(1);
    expect(read.rows[0]?.aliases).toEqual(["peel", "lột da"]);
    expect(read.rows[0]?.description).toBe("Tẩy tế bào");
  });

  it("reads_rows_without_a_header_in_the_default_column_order", () => {
    const read = parseServiceTable("MUN,Điều trị mụn,mụn;trị mụn");

    expect(read.rows[0]).toMatchObject({ code: "MUN", name: "Điều trị mụn", aliases: ["mụn", "trị mụn"] });
  });

  it("lists_rows_it_cannot_read_with_the_line_and_the_reason", () => {
    const read = parseServiceTable("code,name\nOK,Một\nbad code,Hai\nOK,Ba\nNOTNAME,");

    expect(read.rows.map((row) => row.code)).toEqual(["OK"]);
    expect(read.problems.map((problem) => problem.line)).toEqual([3, 4, 5]);
    expect(read.problems[1]?.reason).toMatch(/đã có ở dòng trên/);
    expect(read.problems[2]?.reason).toMatch(/Thiếu tên/);
  });

  it("returns_nothing_for_blank_text", () => {
    expect(parseServiceTable("  \n ")).toEqual({ rows: [], problems: [] });
  });
});

describe("importing", () => {
  const incoming = service({ code: "NAM", name: "Nám", aliases: ["nám má", "NÁM"], description: "", branches: ["HCM"] });

  it("matches_rows_to_the_catalogue_by_code", () => {
    const rows = importRows([incoming, service({ code: "NEW" })], [NAM]);

    expect(rows.map((row) => row.existing?.id ?? null)).toEqual([NAM.id, null]);
  });

  it("updates_by_adding_aliases_and_branches_and_keeping_the_description", () => {
    const body = updateBody(incoming, { ...NAM, description: "Laser", branches: ["Hà Nội"] });

    expect(body.aliases).toEqual(["nám", "nám má"]);
    expect(body.branches).toEqual(["Hà Nội", "HCM"]);
    expect(body.description).toBe("Laser");
    expect(body.name).toBe("Nám");
  });
});
