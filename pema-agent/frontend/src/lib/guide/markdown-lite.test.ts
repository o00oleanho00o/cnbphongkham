import { describe, expect, it } from "vitest";

import { parseInline, parseMarkdown, safeHref } from "./markdown-lite";

describe("parseMarkdown", () => {
  it("reads_headings_paragraphs_and_both_kinds_of_list", () => {
    const blocks = parseMarkdown(
      [
        "Lead line",
        "continues here.",
        "",
        "## Cách thực hiện",
        "",
        "1. Mở **Hôm nay**.",
        "2. Chọn kênh",
        "   rồi ghi kết quả.",
        "",
        "- một",
        "- hai",
      ].join("\n"),
    );
    expect(blocks).toEqual([
      { kind: "paragraph", inline: [{ kind: "text", text: "Lead line continues here." }] },
      { kind: "heading", level: 2, text: "Cách thực hiện" },
      {
        kind: "list",
        ordered: true,
        items: [
          [
            { kind: "text", text: "Mở " },
            { kind: "bold", text: "Hôm nay" },
            { kind: "text", text: "." },
          ],
          [{ kind: "text", text: "Chọn kênh rồi ghi kết quả." }],
        ],
      },
      {
        kind: "list",
        ordered: false,
        items: [[{ kind: "text", text: "một" }], [{ kind: "text", text: "hai" }]],
      },
    ]);
  });

  it("shows_a_title_heading_as_level_two_and_deeper_ones_as_level_three", () => {
    expect(parseMarkdown("# Tiêu đề\n#### Nhỏ")).toEqual([
      { kind: "heading", level: 2, text: "Tiêu đề" },
      { kind: "heading", level: 3, text: "Nhỏ" },
    ]);
  });

  it("keeps_markup_it_does_not_know_as_plain_text_and_never_makes_html", () => {
    const blocks = parseMarkdown("<script>alert(1)</script> và <b>đậm</b>");
    expect(blocks).toEqual([
      {
        kind: "paragraph",
        inline: [{ kind: "text", text: "<script>alert(1)</script> và <b>đậm</b>" }],
      },
    ]);
  });

  it("reads_a_quote_and_ends_a_list_at_a_blank_line", () => {
    expect(parseMarkdown("- a\n\n> chú ý")).toEqual([
      { kind: "list", ordered: false, items: [[{ kind: "text", text: "a" }]] },
      { kind: "quote", inline: [{ kind: "text", text: "chú ý" }] },
    ]);
  });

  it("returns_nothing_for_an_empty_article", () => {
    expect(parseMarkdown("")).toEqual([]);
    expect(parseMarkdown("\n\n   \n")).toEqual([]);
  });
});

describe("parseInline", () => {
  it("reads_bold_italic_code_and_links", () => {
    expect(parseInline("a **b** *c* `d` [e](/today)")).toEqual([
      { kind: "text", text: "a " },
      { kind: "bold", text: "b" },
      { kind: "text", text: " " },
      { kind: "italic", text: "c" },
      { kind: "text", text: " " },
      { kind: "code", text: "d" },
      { kind: "text", text: " " },
      { kind: "link", text: "e", href: "/today" },
    ]);
  });

  it("drops_the_url_of_an_unsafe_link_and_keeps_its_label", () => {
    expect(parseInline("[bấm](javascript:alert)")).toEqual([{ kind: "text", text: "bấm" }]);
  });
});

describe("safeHref", () => {
  it("allows_http_https_and_paths_of_the_app_only", () => {
    expect(safeHref("https://example.test/x")).toBe("https://example.test/x");
    expect(safeHref("/patients")).toBe("/patients");
    expect(safeHref("//evil.test")).toBeNull();
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,x")).toBeNull();
  });
});
