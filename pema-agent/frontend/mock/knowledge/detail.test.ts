import { beforeEach, describe, expect, it } from "vitest";

import { Router, type Ctx } from "../core";
import { registerDetail } from "./detail";
import { chunksOf, outlineOf, takeSections } from "./markdown";
import { resetStore, store } from "./store";

const BASE = "/v1/plugins/knowledge";
const router = new Router();
registerDetail(router);

async function call(method: string, path: string, body: unknown = {}, query = "") {
  const found = router.match(method, path);
  if (!found) throw new Error(`no route ${method} ${path}`);
  const ctx = { params: found.params, query: new URLSearchParams(query), body } as unknown as Ctx;
  return found.route.handler(ctx);
}

const TEXT = ["# Tài liệu", "", "## Giá", "Nội dung giá", "", "### Gói lẻ", "Một buổi", "", "## Kịch bản", "Chốt khách"].join("\n");

beforeEach(resetStore);

describe("markdown helpers", () => {
  it("paths_chunks_by_their_parent_headings", () => {
    expect(chunksOf("s", TEXT).map((chunk) => chunk.path)).toEqual(["Tài liệu > Giá", "Tài liệu > Giá > Gói lẻ", "Tài liệu > Kịch bản"]);
    expect(chunksOf("s", TEXT).map((chunk) => chunk.id)).toEqual(["s-c1", "s-c2", "s-c3"]);
  });

  it("takes_a_section_with_what_is_nested_under_it", () => {
    const positions = outlineOf(TEXT).findIndex((node) => node.title === "Giá");
    const { kept, moved } = takeSections(TEXT, [positions]);
    expect(moved).toContain("Gói lẻ");
    expect(kept).not.toContain("Gói lẻ");
    expect(kept).toContain("Kịch bản");
  });
});

describe("detail routes", () => {
  it("answers_404_for_a_source_that_is_gone", async () => {
    expect((await call("GET", `${BASE}/sources/nope/structure`)).status).toBe(404);
  });

  it("makes_up_a_text_with_several_sections_for_a_seed_source", async () => {
    const reply = await call("GET", `${BASE}/sources/src-seed-1/structure`);
    const body = reply.body as { markdown: string; outline: unknown[] };
    expect(body.markdown.startsWith("# ")).toBe(true);
    expect(body.outline.length).toBeGreaterThanOrEqual(5);
  });

  it("queues_the_source_again_when_the_structure_is_saved", async () => {
    await call("PUT", `${BASE}/sources/src-seed-1/structure`, { markdown: TEXT });
    const source = store.sources.find((item) => item.id === "src-seed-1");
    expect(source?.processing).toBe("queued");
    expect(source?.chunk_count).toBe(3);
    const events = (await call("GET", `${BASE}/sources/src-seed-1/events`)).body as { kind: string }[];
    expect(events[0]?.kind).toBe("edited");
  });

  it("splits_chosen_sections_into_a_staff_source_used_at_once", async () => {
    await call("PUT", `${BASE}/sources/src-seed-1/structure`, { markdown: TEXT });
    const position = outlineOf(TEXT).findIndex((node) => node.title === "Kịch bản");
    const reply = await call("POST", `${BASE}/sources/src-seed-1/split`, { sections: [position], title: "Kịch bản tách" });
    const created = reply.body as { audience: string; approved: boolean; id: string };
    expect(created.audience).toBe("staff");
    expect(created.approved).toBe(true);
    const original = (await call("GET", `${BASE}/sources/src-seed-1/structure`)).body as { markdown: string };
    expect(original.markdown).not.toContain("Chốt khách");
  });

  it("pages_and_searches_chunks_and_keeps_label_changes", async () => {
    await call("PUT", `${BASE}/sources/src-seed-1/structure`, { markdown: TEXT });
    const found = (await call("GET", `${BASE}/sources/src-seed-1/chunks`, {}, "q=chot")).body as { items: { id: string }[]; total: number };
    expect(found.total).toBe(1);
    await call("PATCH", `${BASE}/chunks/src-seed-1-c1`, { kind: "faq", services: ["NAM"] });
    const all = (await call("GET", `${BASE}/sources/src-seed-1/chunks`)).body as { items: { kind: string; services: string[] }[] };
    expect(all.items[0]).toMatchObject({ kind: "faq", services: ["NAM"] });
  });

  it("restores_an_earlier_text_as_a_new_version", async () => {
    await call("PUT", `${BASE}/sources/src-seed-1/structure`, { markdown: TEXT });
    const events = (await call("GET", `${BASE}/sources/src-seed-1/events`)).body as { id: string }[];
    await call("PUT", `${BASE}/sources/src-seed-1/structure`, { markdown: "# Khác\n\n## Mục\nchữ" });
    const reply = await call("POST", `${BASE}/sources/src-seed-1/restore`, { event: events[0]?.id });
    expect((reply.body as { version: string }).version).toBe("2.1");
    expect(store.markdown.get("src-seed-1")).toBe(TEXT);
  });

  it("refuses_to_restore_from_an_event_that_changed_no_text", async () => {
    const events = (await call("GET", `${BASE}/sources/src-seed-1/events`)).body as { id: string }[];
    expect((await call("POST", `${BASE}/sources/src-seed-1/restore`, { event: events[0]?.id })).status).toBe(409);
  });
});
