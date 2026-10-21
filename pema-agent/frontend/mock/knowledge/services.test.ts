import { beforeEach, describe, expect, it } from "vitest";

import type { Service } from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { Router, type Ctx } from "../core";
import { registerServices } from "./services";
import { resetStore, store } from "./store";

const BASE = "/v1/plugins/knowledge/services";
const router = new Router();
registerServices(router);

async function call(method: string, path: string, body: unknown = {}) {
  const found = router.match(method, path);
  if (!found) throw new Error(`no route ${method} ${path}`);
  const ctx = { params: found.params, query: new URLSearchParams(), body } as unknown as Ctx;
  return found.route.handler(ctx);
}

const NEW_SERVICE = {
  code: "SEO",
  name: "Chăm sóc sẹo",
  aliases: ["sẹo"],
  description: "",
  branches: [],
  enabled: true,
};

beforeEach(resetStore);

describe("services routes", () => {
  it("adds_a_service_that_the_list_then_shows", async () => {
    const created = await call("POST", BASE, NEW_SERVICE);
    const listed = (await call("GET", BASE)).body as Service[];

    expect(created.status).toBe(201);
    expect(listed.map((service) => service.code)).toContain("SEO");
  });

  it("refuses_a_code_in_use_or_with_a_space_and_upper_cases_the_rest", async () => {
    expect((await call("POST", BASE, { ...NEW_SERVICE, code: "NAM" })).status).toBe(422);
    expect((await call("POST", BASE, { ...NEW_SERVICE, code: "seo" })).status).toBe(201);
    expect((await call("POST", BASE, { ...NEW_SERVICE, code: "SE O" })).status).toBe(422);
  });

  it("saves_aliases_at_once", async () => {
    const reply = await call("PATCH", `${BASE}/svc-hori`, { aliases: ["hori", "hori laser"] });

    expect((reply.body as Service).aliases).toEqual(["hori", "hori laser"]);
    expect(store.services.find((service) => service.id === "svc-hori")?.aliases).toHaveLength(2);
  });

  it("renames_the_code_inside_the_sources_that_carry_it", async () => {
    await call("PATCH", `${BASE}/svc-hori`, { code: "HORI_LASER" });

    expect(store.sources.find((source) => source.id === "src-seed-1")?.services).toContain(
      "HORI_LASER",
    );
    expect(store.sources.some((source) => source.services.includes("HORI"))).toBe(false);
  });

  it("deletes_a_service_and_takes_its_code_off_the_sources", async () => {
    const reply = await call("DELETE", `${BASE}/svc-nam`);

    expect(reply.status).toBe(204);
    expect(store.services.some((service) => service.code === "NAM")).toBe(false);
    expect(store.sources.some((source) => source.services.includes("NAM"))).toBe(false);
  });

  it("answers_404_for_a_service_that_is_gone", async () => {
    expect((await call("PATCH", `${BASE}/nope`, {})).status).toBe(404);
    expect((await call("DELETE", `${BASE}/nope`)).status).toBe(404);
  });

  it("reads_a_pasted_markdown_table_into_a_preview_without_saving", async () => {
    const text =
      "| code | name | aliases |\n|---|---|---|\n| LAN | Triệt lông | lông; wax |\n| NAM | Nám | nám |";
    const preview = (await call("POST", `${BASE}/import`, { text })).body as Service[];

    expect(preview.map((service) => service.code)).toEqual(["LAN", "NAM"]);
    expect(preview[1]?.chunk_count).toBe(38);
    expect(store.services.some((service) => service.code === "LAN")).toBe(false);
  });
});
