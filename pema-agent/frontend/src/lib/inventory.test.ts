import { describe, expect, it } from "vitest";

import {
  checkAllTestFilesListed,
  checkRoutes,
  checkTestIds,
  hasTestTitle,
  routeRows,
  testIds,
} from "../../scripts/inventory-lib";

const TABLE = [
  "| Route | Screen | Capabilities | Test ids | Owner |",
  "| --- | --- | --- | --- | --- |",
  "| `/today` | Hôm nay | list | `src/a.test.tsx::lists tasks`; `src/b.test.ts` | U1 |",
  "| `/patients/[id]` | 360 | read | none | U1 |",
].join("\n");

describe("feature inventory checks", () => {
  it("reads_the_route_of_every_row_of_the_table", () => {
    expect(routeRows(TABLE)).toEqual([{ route: "/today" }, { route: "/patients/[id]" }]);
  });

  it("reads_whole_file_and_titled_test_ids", () => {
    expect(testIds(TABLE)).toEqual([
      { file: "src/a.test.tsx", title: "lists tasks" },
      { file: "src/b.test.ts", title: null },
    ]);
  });

  it("finds_a_title_in_it_test_and_describe_calls_only", () => {
    const source = `describe("Inbox", () => { it("lists tasks", () => {}); });\nconst x = "not a test";`;

    expect(hasTestTitle(source, "lists tasks")).toBe(true);
    expect(hasTestTitle(source, "Inbox")).toBe(true);
    expect(hasTestTitle(source, "not a test")).toBe(false);
  });

  it("reports_a_route_without_a_page_and_a_page_without_a_row", () => {
    const problems = checkRoutes([{ route: "/today" }, { route: "/gone" }], ["/today", "/new"]);

    expect(problems).toEqual([
      "route /gone has no page.tsx",
      "page /new has no row in the inventory",
    ]);
  });

  it("reports_a_missing_test_file_and_a_missing_title", () => {
    const files: Record<string, string> = { "src/a.test.tsx": `it("other", () => {});` };
    const problems = checkTestIds(
      [
        { file: "src/a.test.tsx", title: "lists tasks" },
        { file: "src/gone.test.ts", title: null },
      ],
      (file) => files[file] ?? null,
    );

    expect(problems).toEqual([
      `test "lists tasks" is not in src/a.test.tsx`,
      "test file src/gone.test.ts does not exist",
    ]);
  });

  it("reports_a_test_file_the_inventory_does_not_name", () => {
    const problems = checkAllTestFilesListed(
      [{ file: "src/a.test.ts" }],
      ["src/a.test.ts", "src/b.test.ts"],
    );

    expect(problems).toEqual(["test file src/b.test.ts is not named in the inventory"]);
  });
});
