import { beforeEach, describe, expect, it } from "vitest";

import { Router, type Ctx } from "../core";
import type {
  ConfirmItem,
  ConfirmResult,
  PreviewInput,
  PreviewResult,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { registerAdd } from "./add";
import { parseInput, readHead } from "./parse";
import { registerSources } from "./sources";
import { resetStore, store } from "./store";

const BASE = "/v1/plugins/knowledge";
// Sources first, as `index.ts` registers them: the `{id}` routes must not swallow preview and confirm.
const router = new Router();
registerSources(router);
registerAdd(router);

async function call<T>(method: string, path: string, body: unknown = {}): Promise<{ status: number; body: T }> {
  const found = router.match(method, path);
  if (!found) throw new Error(`no route ${method} ${path}`);
  const ctx = { params: found.params, query: new URLSearchParams(), body } as unknown as Ctx; // the handlers read these three
  const reply = await found.route.handler(ctx);
  return { status: reply.status ?? 200, body: reply.body as T };
}

const HEAD = (extra: string) =>
  `---\ndoc_id: DEMO-PEMA-D30\ntenant_id: DEMO-PEMA\ntitle: "Bảng giá thử"\nversion: "2.0"\nstatus: active\neffective_from: "2026-10-01"\neffective_to: null\n${extra}---\n`;

const LONG = "Một buổi laser điều trị nám kéo dài 60 phút, bác sĩ tư vấn trước khi thực hiện và dặn dò chăm sóc sau điều trị. ".repeat(3);
const PRICE_DOC = `${HEAD("audience: patient\n")}\n# Bảng giá\n\n## Giá lẻ\n${LONG}\n\n### Buổi nám\n${LONG}\n\n### Ghi chú\nNgắn.\n\n## Bảng\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n`;

const text = (key: string, body: string, name = `${key}.md`): PreviewInput => ({ key, name, kind: "file", size: body.length, text: body });
const base64 = (key: string, name: string): PreviewInput => ({ key, name, kind: "file", size: 5000, base64: "QUJD" });

async function preview(...inputs: PreviewInput[]): Promise<PreviewResult> {
  return (await call<PreviewResult>("POST", `${BASE}/sources/preview`, { inputs })).body;
}

beforeEach(resetStore);

describe("readHead", () => {
  it("reads_the_head_like_the_plugin_does", () => {
    const { meta, body } = readHead(PRICE_DOC.replace(/\n/g, "\r\n"));
    expect(meta).toMatchObject({ doc_code: "DEMO-PEMA-D30", audience: "patient", lifecycle: "active", effective_to: null });
    expect(body).toContain("# Bảng giá");
  });
});

describe("preview", () => {
  it("builds_the_outline_chunks_and_counts_tables", async () => {
    const { items } = await preview(text("a", PRICE_DOC));
    const [item] = items;
    expect(item?.outline.map((node) => [node.level, node.title])).toEqual([
      [1, "Bảng giá"],
      [2, "Giá lẻ"],
      [3, "Buổi nám"],
      [3, "Ghi chú"],
      [2, "Bảng"],
    ]);
    // "Ghi chú" (5 chars) joins the previous section, so it counts no chunk of its own.
    expect(item?.outline.find((node) => node.title === "Ghi chú")?.chunks).toBe(0);
    expect(item?.tables_split).toBe(1);
    expect(item?.chunk_count).toBeGreaterThan(0);
    expect(item?.avg_chars).toBeGreaterThan(0);
  });

  it("warns_when_there_is_no_heading", async () => {
    const { items } = await preview(text("a", "Chỉ là một đoạn văn."));
    expect(items[0]?.warnings.map((warning) => warning.code)).toContain("no_headings");
  });

  it("finds_phone_numbers_and_emails", async () => {
    const { items } = await preview(text("a", "# T\n\n## Liên hệ\nGọi 0912345678 hoặc mail lan@example.vn"));
    expect(items[0]?.warnings.find((warning) => warning.code === "personal_data")?.text).toContain("email");
  });

  it("warns_about_internal_sections_in_a_patient_document", async () => {
    const { items } = await preview(text("a", `${HEAD("audience: patient\n")}# T\n\n## Kịch bản chốt khách\nNói thế này.`));
    expect(items[0]?.warnings.find((warning) => warning.code === "internal_script")?.level).toBe("warn");
  });

  it("does_not_flag_internal_sections_in_a_staff_document", async () => {
    const { items } = await preview(text("a", `${HEAD("audience: staff\n")}# T\n\n## Kịch bản chốt khách\nNói thế này.`));
    expect(items[0]?.warnings.map((warning) => warning.code)).not.toContain("internal_script");
  });

  it("flags_a_challenge_file_as_an_error_unless_benchmark_is_on", async () => {
    const challenge = text("a", `${HEAD("ingest_role: challenge\n")}# Giá cũ\n\n## Giá\n${LONG}`);
    expect((await preview(challenge)).items[0]?.warnings.find((warning) => warning.code === "challenge")?.level).toBe("error");
    store.settings.benchmark_mode = true;
    const again = await preview(challenge);
    expect(again.benchmark).toBe(true);
    expect(again.items[0]?.warnings.map((warning) => warning.code)).not.toContain("challenge");
  });

  it("refuses_a_document_of_another_clinic", async () => {
    const other = PRICE_DOC.replace("tenant_id: DEMO-PEMA", "tenant_id: OTHER-CLINIC");
    const { items } = await preview(text("a", other));
    expect(items[0]?.warnings.find((warning) => warning.code === "tenant")?.level).toBe("error");
  });

  it("points_to_a_source_with_the_same_code", async () => {
    const same = PRICE_DOC.replace("DEMO-PEMA-D30", "DEMO-PEMA-D07");
    const { items } = await preview(text("a", same));
    expect(items[0]?.same_code_as?.id).toBe("src-seed-1");
  });

  it("points_to_a_source_with_the_same_title_when_the_code_differs", async () => {
    const { items } = await preview(text("a", "# T\n\n## M\nx", "Giờ mở cửa dịp lễ.md"));
    expect(items[0]?.warnings.map((warning) => warning.code)).toContain("same_title");
  });

  it("reads_a_scan_pdf_as_an_error_and_other_files_from_their_name", async () => {
    const { items } = await preview(base64("s", "phieu-scan.pdf"), base64("p", "cam-nang.pdf"), base64("d", "bang.docx"));
    expect(items[0]?.error).toBe("PDF là ảnh scan, chưa đọc được chữ");
    expect([items[1]?.chunk_count, items[1]?.warnings.map((warning) => warning.code)]).toEqual([12, ["no_headings"]]);
    expect([items[2]?.chunk_count, items[2]?.outline.length]).toEqual([12, 3]);
  });
});

function confirmItem(key: string, patch: Partial<ConfirmItem> = {}): ConfirmItem {
  return {
    key,
    title: "Bảng giá thử",
    doc_code: "DEMO-PEMA-D30",
    audience: "patient",
    approved: true,
    services: [],
    lifecycle: "active",
    version: "2.0",
    effective_from: "2026-10-01",
    effective_to: null,
    supersedes: null,
    note: "",
    on_same_code: "version",
    ...patch,
  };
}

describe("confirm", () => {
  it("creates_queued_sources_with_the_preview_chunk_count_and_keeps_the_markdown", async () => {
    const read = await preview(text("a", PRICE_DOC));
    const { body } = await call<ConfirmResult>("POST", `${BASE}/sources/confirm`, { preview_id: read.preview_id, items: [confirmItem("a")] });
    const [created] = body.created;
    expect(created).toMatchObject({ processing: "queued", chunk_count: read.items[0]?.chunk_count, approved: true, audience: "patient" });
    expect(store.sources[0]?.id).toBe(created?.id);
    expect(store.markdown.get(created?.id ?? "")).toContain("## Giá lẻ");
    expect(store.events.get(created?.id ?? "")?.map((event) => event.kind)).toContain("uploaded");
  });

  it("supersedes_the_replaced_source_and_records_the_event", async () => {
    const read = await preview(text("a", PRICE_DOC));
    await call("POST", `${BASE}/sources/confirm`, { preview_id: read.preview_id, items: [confirmItem("a", { supersedes: "src-seed-1" })] });
    expect(store.sources.find((source) => source.id === "src-seed-1")?.lifecycle).toBe("superseded");
    expect(store.events.get("src-seed-1")?.map((event) => event.kind)).toContain("replaced");
  });

  it("leaves_out_a_file_the_person_chose_to_skip_and_says_why", async () => {
    const same = PRICE_DOC.replace("DEMO-PEMA-D30", "DEMO-PEMA-D07");
    const read = await preview(text("a", same));
    const { body } = await call<ConfirmResult>("POST", `${BASE}/sources/confirm`, {
      preview_id: read.preview_id,
      items: [confirmItem("a", { doc_code: "DEMO-PEMA-D07", on_same_code: "skip" })],
    });
    expect(body.created).toHaveLength(0);
    expect(body.skipped[0]?.reason).toContain("DEMO-PEMA-D07");
  });

  it("remembers_the_content_so_the_next_preview_says_it_is_the_same", async () => {
    const read = await preview(text("a", PRICE_DOC));
    await call("POST", `${BASE}/sources/confirm`, { preview_id: read.preview_id, items: [confirmItem("a")] });
    const again = await preview(text("b", PRICE_DOC));
    expect(again.items[0]?.same_content_as?.title).toBe("Bảng giá thử");
  });

  it("answers_404_for_a_preview_it_does_not_know", async () => {
    expect((await call("POST", `${BASE}/sources/confirm`, { preview_id: "nope", items: [] })).status).toBe(404);
  });

  it("is_not_swallowed_by_the_source_id_routes", () => {
    expect(router.match("POST", `${BASE}/sources/preview`)?.route.template).toBe(`${BASE}/sources/preview`);
    expect(router.match("POST", `${BASE}/sources/confirm`)?.route.template).toBe(`${BASE}/sources/confirm`);
  });
});

describe("parseInput", () => {
  it("gives_a_text_input_the_text_format", () => {
    const parsed = parseInput({ key: "text", name: "Câu hỏi", kind: "text", size: 20, text: "# A\n\n## B\nnội dung" });
    expect(parsed.item.format).toBe("text");
  });
});
