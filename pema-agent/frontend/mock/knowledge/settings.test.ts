import { beforeEach, describe, expect, it } from "vitest";

import type {
  EmbeddingTest,
  KnowledgeSettings,
  ParserTest,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { Router, type Ctx } from "../core";
import { registerSettings } from "./settings";
import { resetStore, store } from "./store";

const BASE = "/v1/plugins/knowledge/settings";
const router = new Router();
registerSettings(router);

async function call(method: string, path: string, body: unknown = {}) {
  const found = router.match(method, path);
  if (!found) throw new Error(`no route ${method} ${path}`);
  const ctx = { params: found.params, query: new URLSearchParams(), body } as unknown as Ctx;
  return found.route.handler(ctx);
}

const patch = (body: unknown) => call("PATCH", BASE, body);

beforeEach(resetStore);

describe("settings routes", () => {
  it("merges_a_patch_and_marks_only_the_touched_group_as_saved", async () => {
    const reply = await patch({ embedding: { model: "other-model" } });
    const body = reply.body as KnowledgeSettings;

    expect(body.embedding).toMatchObject({ model: "other-model", origin: "saved" });
    expect(body.parser.origin).toBe("profile");
    expect(body.search.results).toBe(8);
  });

  it("remembers_a_key_without_ever_sending_it_back", async () => {
    const reply = await patch({ embedding: { api_key: "sk-fictional-key" } });

    expect((reply.body as KnowledgeSettings).embedding.has_key).toBe(true);
    expect(JSON.stringify(reply.body)).not.toContain("sk-fictional-key");
    expect(JSON.stringify(store.settings)).not.toContain("sk-fictional-key");
    expect(((await patch({ embedding: { api_key: "" } })).body as KnowledgeSettings).embedding.has_key).toBe(false);
  });

  it("refuses_numbers_outside_their_ranges", async () => {
    expect((await patch({ search: { results: 0 } })).status).toBe(422);
    expect((await patch({ embedding: { dimensions: 99999 } })).status).toBe(422);
    expect(store.settings.search.results).toBe(8);
  });

  it("goes_back_to_the_configuration_for_a_reset_group", async () => {
    await patch({ parser: { kind: "docling", docling_url: "http://docling.test" } });
    const reply = await patch({ reset: ["parser"] });

    expect((reply.body as KnowledgeSettings).parser).toEqual({ kind: "simple", docling_url: "", origin: "profile" });
  });

  it("says_why_the_embedding_test_fails_until_an_address_and_a_key_are_saved", async () => {
    const noAddress = (await call("POST", `${BASE}/test-embedding`)).body as EmbeddingTest;
    await patch({ embedding: { base_url: "https://embed.example.test/v1" } });
    const noKey = (await call("POST", `${BASE}/test-embedding`)).body as EmbeddingTest;
    await patch({ embedding: { api_key: "k" } });
    const good = (await call("POST", `${BASE}/test-embedding`)).body as EmbeddingTest;

    expect([noAddress.message, noKey.message]).toEqual(["Chưa có địa chỉ", "Chưa có khóa API"]);
    expect(good).toMatchObject({ ok: true, dimensions: 1024, normalised: true, ms: 1840 });
  });

  it("queues_every_chunk_and_zeroes_the_count_without_a_vector", async () => {
    const reply = (await call("POST", `${BASE}/reembed`)).body as { queued: number };

    expect(reply.queued).toBeGreaterThan(0);
    expect(store.settings.embedding.chunks_without_vector).toBe(0);
  });

  it("tests_the_parser_by_its_kind", async () => {
    expect(((await call("POST", `${BASE}/test-parser`)).body as ParserTest).ok).toBe(true);
    await patch({ parser: { kind: "docling" } });
    expect(((await call("POST", `${BASE}/test-parser`)).body as ParserTest).ok).toBe(false);
  });
});
