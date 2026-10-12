import { describe, expect, it } from "vitest";

import { readFrontmatter } from "./frontmatter";

const HEAD = [
  "---",
  "doc_id: DEMO-PEMA-D07",
  "tenant_id: DEMO-PEMA",
  'title: "Pema Clinic & Spa (demo): bảng giá hiện hành"',
  'version: "2.0"',
  "status: active",
  'effective_from: "2026-10-01"',
  "effective_to: null",
  "ingest_role: kb",
  "audience: patient",
  "---",
  "",
  "# Bảng giá",
].join("\n");

describe("readFrontmatter", () => {
  it("reads_the_fields_and_leaves_the_body", () => {
    const { meta, body } = readFrontmatter(HEAD);
    expect(meta).toEqual({
      doc_code: "DEMO-PEMA-D07",
      title: "Pema Clinic & Spa (demo): bảng giá hiện hành",
      tenant_id: "DEMO-PEMA",
      version: "2.0",
      lifecycle: "active",
      effective_from: "2026-10-01",
      effective_to: null,
      audience: "patient",
      ingest_role: "kb",
    });
    expect(body.trim()).toBe("# Bảng giá");
  });

  it("reads_crlf_and_single_quotes", () => {
    const { meta } = readFrontmatter("---\r\ndoc_id: 'A-1'\r\naudience: staff\r\n---\r\ntext");
    expect(meta.doc_code).toBe("A-1");
    expect(meta.audience).toBe("staff");
  });

  it("gives_empty_meta_without_a_head", () => {
    const { meta, body } = readFrontmatter("# Chỉ có tiêu đề");
    expect(meta.doc_code).toBeNull();
    expect(meta.audience).toBeNull();
    expect(body).toBe("# Chỉ có tiêu đề");
  });

  it("gives_empty_meta_when_the_head_is_never_closed", () => {
    const text = "---\ndoc_id: X\n# Tiêu đề";
    expect(readFrontmatter(text)).toEqual({ meta: readFrontmatter("").meta, body: text });
  });

  it("ignores_malformed_lines_and_unknown_values", () => {
    const { meta } = readFrontmatter(
      "---\nnot a pair\nstatus: weird\naudience: everyone\neffective_from: yesterday\nversion: ~\n---\n",
    );
    expect(meta.lifecycle).toBeNull();
    expect(meta.audience).toBeNull();
    expect(meta.effective_from).toBeNull();
    expect(meta.version).toBeNull();
  });

  it("keeps_adversarial_and_drops_a_trailing_comment", () => {
    const { meta } = readFrontmatter("---\nstatus: adversarial # thử\ningest_role: challenge\n---\n");
    expect(meta.lifecycle).toBe("adversarial");
    expect(meta.ingest_role).toBe("challenge");
  });

  it("strips_a_byte_order_mark", () => {
    expect(readFrontmatter("﻿---\ndoc_id: B\n---\n").meta.doc_code).toBe("B");
  });
});
