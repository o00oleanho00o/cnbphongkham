import { beforeEach, describe, expect, it } from "vitest";

import { type Ctx, Router } from "../core";
import { registerSources } from "./sources";
import { resetStore, store } from "./store";

const BASE = "/v1/plugins/knowledge";
let router: Router;

beforeEach(() => {
  resetStore();
  router = new Router();
  registerSources(router);
});

async function call(method: string, path: string, body: unknown = {}) {
  const [pathname = "", search = ""] = path.split("?");
  const found = router.match(method, pathname);
  if (!found) return null;
  const ctx = { params: found.params, query: new URLSearchParams(search), body } as unknown as Ctx;
  return found.route.handler(ctx);
}

describe("mock knowledge sources", () => {
  it("lists_with_summary_and_warnings", async () => {
    const reply = await call("GET", `${BASE}/sources`);
    const body = reply?.body as { total: number; warnings: string[]; summary: { errors: number } };
    expect(body.total).toBe(store.sources.length);
    expect(body.summary.errors).toBe(1);
    expect(body.warnings).toContain("Embedding chưa kết nối: đang tìm bằng từ khóa");
  });

  it("filters_by_text_without_accents_and_by_unapproved", async () => {
    const text = (await call("GET", `${BASE}/sources?q=cam%20nang`))?.body as { total: number };
    expect(text.total).toBe(1);
    const open = (await call("GET", `${BASE}/sources?approved=false`))?.body as { items: { approved: boolean }[] };
    expect(open.items.every((item) => !item.approved)).toBe(true);
  });

  it("processing_sources_advance_to_ready_over_calls", async () => {
    await Promise.all([1, 2, 3, 4, 5].map(() => call("GET", `${BASE}/sources`)));
    expect(store.sources.find((item) => item.id === "src-seed-4")?.processing).toBe("ready");
  });

  it("bulk_is_not_taken_for_a_source_id", async () => {
    const reply = await call("POST", `${BASE}/sources/bulk`, { ids: ["src-seed-3", "nope"], action: "approve" });
    expect(reply?.body).toEqual({ done: 1, failed: [{ id: "nope", message: "Không tìm thấy nguồn này." }] });
    expect(store.sources.find((item) => item.id === "src-seed-3")?.approved_by).toBe("Quản trị");
    expect(store.events.get("src-seed-3")?.map((event) => event.kind)).toEqual(["approved"]);
  });

  it("bulk_delete_removes_the_rows", async () => {
    await call("POST", `${BASE}/sources/bulk`, { ids: ["src-seed-6"], action: "delete" });
    expect(store.sources.some((item) => item.id === "src-seed-6")).toBe(false);
  });

  it("approving_a_source_in_error_is_refused", async () => {
    const reply = await call("POST", `${BASE}/sources/src-seed-5/approve`);
    expect(reply?.status).toBe(409);
  });
});
