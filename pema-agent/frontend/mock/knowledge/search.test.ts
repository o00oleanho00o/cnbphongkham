// The fake search ("Thử tìm") and the gaps routes of the fake knowledge store.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import type { Gap, SearchDebug } from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { startMockServer } from "../server";
import { fold } from "./search-engine";
import { resetStore, store } from "./store";

let server: Server;
let base: string;
let token = "";

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const login = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "owner@pema.test", password: "demo1234" }),
  });
  const cookie = login.headers.get("set-cookie")?.split(";")[0] ?? "";
  const issued = await fetch(`${base}/api/v1/auth/agent-token`, {
    method: "POST",
    headers: { cookie },
  });
  token = ((await issued.json()) as { token: string }).token;
});
afterAll(() => {
  server.close();
});
beforeEach(() => {
  resetStore();
});

const call = (method: string, path: string, body?: unknown) =>
  fetch(`${base}/v1/plugins/knowledge${path}`, {
    method,
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

const search = async (question: string, channel: "patient" | "staff") => {
  const res = await call("POST", "/search/debug", { question, channel, as_of: "2026-10-12" });
  return { res, body: (await res.json()) as SearchDebug };
};
const stageOf = (result: SearchDebug, id: string) => result.stages.find((stage) => stage.id === id);

describe("fold", () => {
  it("removes_diacritics_and_turns_d_bar_into_d", () => {
    expect(fold("Đồi mồi, TRỊ NÁM?")).toBe("doi moi, tri nam?");
  });
});

describe("POST /search/debug", () => {
  it("recognises_a_service_by_alias_and_lists_six_stages_in_order", async () => {
    const { res, body } = await search("Giá trị nám bao nhiêu?", "staff");

    expect(res.status).toBe(200);
    expect(body.services).toContain("NAM");
    expect(body.stages.map((stage) => stage.id)).toEqual([
      "understand",
      "keyword",
      "vector",
      "fused",
      "reranked",
      "final",
    ]);
    expect(stageOf(body, "final")?.candidates.length).toBeGreaterThan(0);
  });

  it("skips_the_vector_branch_without_an_embedding_key", async () => {
    const { body } = await search("giá nám", "staff");

    expect(stageOf(body, "vector")).toMatchObject({
      skipped: true,
      note: "Embedding chưa kết nối: bỏ qua nhánh vector",
    });
  });

  it("shows_internal_sources_on_every_channel_while_the_store_is_shared", async () => {
    const { body } = await search("quy trình tư vấn nội bộ", "patient");

    expect(body.stages.at(-1)?.candidates.some((c) => c.doc_code === "DEMO-PEMA-D19")).toBe(true);
  });

  it("leaves_out_a_source_outside_its_dates_on_the_patient_channel", async () => {
    const { body } = await search("giá nám", "patient");
    const codes = stageOf(body, "final")?.candidates.map((c) => c.doc_code) ?? [];

    expect(codes).not.toContain("DEMO-PEMA-D07-V1");
    expect(codes).toContain("DEMO-PEMA-D07");
  });

  it("gives_chunk_ids_that_end_in_the_source_id_and_c_number", async () => {
    const { body } = await search("giá nám", "staff");

    expect(stageOf(body, "final")?.candidates.every((c) => /^src-.+-c\d+$/.test(c.chunk_id))).toBe(
      true,
    );
  });

  it("says_so_when_nothing_matches", async () => {
    const { body } = await search("zzzz qqqq", "patient");
    const final = stageOf(body, "final");

    expect(final?.candidates).toEqual([]);
    expect(final?.note).toContain("Không có đoạn nào");
  });

  it("refuses_an_empty_question_and_a_bad_channel", async () => {
    expect(
      (
        await call("POST", "/search/debug", {
          question: " ",
          channel: "staff",
          as_of: "2026-10-12",
        })
      ).status,
    ).toBe(400);
    expect(
      (await call("POST", "/search/debug", { question: "x", channel: "web", as_of: "2026-10-12" }))
        .status,
    ).toBe(400);
  });
});

describe("gaps routes", () => {
  it("lists_open_gaps_and_moves_one_to_ignored_and_back", async () => {
    const open = (await (await call("GET", "/gaps?state=open")).json()) as Gap[];
    expect(open).toHaveLength(store.gaps.length);

    const patched = await call("PATCH", `/gaps/${open[0]?.id}`, { state: "ignored" });
    expect(patched.status).toBe(200);
    expect((await (await call("GET", "/gaps?state=ignored")).json()) as Gap[]).toHaveLength(1);
    expect((await (await call("GET", "/gaps?state=open")).json()) as Gap[]).toHaveLength(
      open.length - 1,
    );

    await call("PATCH", `/gaps/${open[0]?.id}`, { state: "open" });
    expect((await (await call("GET", "/gaps?state=open")).json()) as Gap[]).toHaveLength(
      open.length,
    );
  });

  it("answers_404_for_an_unknown_gap_and_400_for_a_bad_state", async () => {
    expect((await call("PATCH", "/gaps/nope", { state: "ignored" })).status).toBe(404);
    expect((await call("PATCH", `/gaps/${store.gaps[0]?.id}`, { state: "x" })).status).toBe(400);
  });
});
