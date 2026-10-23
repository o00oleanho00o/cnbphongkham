// Routes of the fake knowledge store: settings, the connection tests and re-embedding. A key is never sent back:
// the store only remembers whether one was saved.
import type {
  EmbeddingSettings,
  SettingsPatch,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import {
  RANGES,
  type SettingsChange,
  numberProblem,
  urlProblem,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/settings/settings-logic";
import { type Reply, type Router, bodyOf } from "../core";
import { store } from "./store";

const BASE = "/v1/plugins/knowledge/settings";

/** What "Về mặc định" goes back to: the agent's own configuration (the same as the seed of the store). */
const PROFILE_EMBEDDING: Omit<EmbeddingSettings, "chunks_without_vector"> = {
  base_url: "",
  model: "qwen/qwen3-embedding-8b",
  dimensions: 1024,
  query_prefix: "",
  document_prefix: "",
  has_key: false,
  origin: "profile",
};

const refuse = (detail: string): Reply => ({ status: 422, body: { detail } });

const totalChunks = (): number =>
  store.sources.reduce((sum, source) => sum + source.chunk_count, 0);

/** The first reason a patch cannot be applied, or null. */
function problemOf(patch: SettingsPatch): string | null {
  const { embedding, search } = patch;
  const checks = [
    embedding?.dimensions === undefined
      ? null
      : numberProblem(String(embedding.dimensions), RANGES.dimensions),
    embedding?.base_url === undefined ? null : urlProblem(embedding.base_url, "Địa chỉ", false),
    embedding?.model === undefined || embedding.model.trim() !== ""
      ? null
      : "Model: nhập tên model.",
    search?.results === undefined ? null : numberProblem(String(search.results), RANGES.results),
    search?.min_score === undefined
      ? null
      : numberProblem(String(search.min_score), RANGES.min_score),
    search?.char_budget === undefined
      ? null
      : numberProblem(String(search.char_budget), RANGES.char_budget),
  ];
  return checks.find((text) => text !== null) ?? null;
}

/** Another model, size or prefix means every vector is out of date. */
function embeddingChanged(
  patch: NonNullable<SettingsPatch["embedding"]>,
  now: EmbeddingSettings,
): boolean {
  const keys = ["model", "dimensions", "query_prefix", "document_prefix"] as const;
  return keys.some((key) => patch[key] !== undefined && patch[key] !== now[key]);
}

function patchEmbedding(patch: NonNullable<SettingsPatch["embedding"]>): EmbeddingSettings {
  const now = store.settings.embedding;
  const { api_key: key, ...fields } = patch;
  return {
    ...now,
    ...fields,
    has_key: key === undefined ? now.has_key : key !== "",
    origin: "saved",
    chunks_without_vector: embeddingChanged(patch, now) ? totalChunks() : now.chunks_without_vector,
  };
}

function resetGroups(groups: NonNullable<SettingsChange["reset"]>): void {
  const settings = store.settings;
  store.settings = {
    ...settings,
    embedding: groups.includes("embedding")
      ? { ...PROFILE_EMBEDDING, chunks_without_vector: totalChunks() }
      : settings.embedding,
  };
}

function applyPatch(change: SettingsChange): Reply {
  const { reset, ...patch } = change;
  const problem = problemOf(patch);
  if (problem) return refuse(problem);
  const settings = store.settings;
  resetGroups(reset ?? []);
  store.settings = {
    ...store.settings,
    embedding: patch.embedding ? patchEmbedding(patch.embedding) : store.settings.embedding,
    judging: { ...settings.judging, ...patch.judging },
    search: { ...settings.search, ...patch.search },
    benchmark_mode: patch.benchmark_mode ?? settings.benchmark_mode,
  };
  return { body: store.settings };
}

function testEmbedding(): Reply {
  const { base_url: baseUrl, has_key: hasKey, dimensions } = store.settings.embedding;
  const fail = (message: string): Reply => ({
    body: { ok: false, dimensions: null, normalised: null, ms: null, message },
  });
  if (baseUrl.trim() === "") return fail("Chưa có địa chỉ");
  if (!hasKey) return fail("Chưa có khóa API");
  return { body: { ok: true, dimensions, normalised: true, ms: 1840, message: "Kết nối tốt" } };
}

function reembed(): Reply {
  const queued = totalChunks();
  store.settings = {
    ...store.settings,
    embedding: { ...store.settings.embedding, chunks_without_vector: 0 },
  };
  return { body: { queued } };
}

export function registerSettings(router: Router): void {
  router.get(BASE, null, (): Reply => ({ body: store.settings }));
  router.patch(BASE, null, (ctx): Reply => applyPatch(bodyOf<SettingsChange>(ctx)));
  router.post(`${BASE}/test-embedding`, null, testEmbedding);
  router.post(`${BASE}/reembed`, null, reembed);
}
