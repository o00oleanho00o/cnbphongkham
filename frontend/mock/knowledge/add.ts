// Routes of the fake knowledge store for adding sources: `POST /sources/preview` reads the inputs (nothing is added),
// `POST /sources/confirm` turns a preview into sources. Both are POST on a literal path; no route of `sources.ts`
// is a POST on a lone `{id}`, so `Router.match` (first match wins) cannot swallow them whatever the order.
import { type Reply, type Router, bodyOf } from "../core";
import type {
  ConfirmItem,
  ConfirmResult,
  PreviewInput,
  PreviewResult,
  Source,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { type Parsed, parseInput, rememberHash } from "./parse";
import { nextId, nowIso, store } from "./store";

const BASE = "/v1/plugins/knowledge";
const ADMIN = "Quản trị";

/** What a preview keeps for its confirm: the parsed files by key. */
interface Kept {
  parsed: Map<string, Parsed>;
}

function isKept(value: unknown): value is Kept {
  return typeof value === "object" && value !== null && "parsed" in value;
}

function preview(inputs: readonly PreviewInput[]): PreviewResult {
  const parsed = inputs.map(parseInput);
  const id = nextId("prv");
  store.previews.set(id, {
    parsed: new Map(parsed.map((entry) => [entry.item.key, entry])),
  } satisfies Kept);
  return {
    preview_id: id,
    items: parsed.map((entry) => entry.item),
    benchmark: store.settings.benchmark_mode,
  };
}

function addEvent(id: string, kind: string, note: string): void {
  const events = store.events.get(id) ?? [];
  store.events.set(id, [...events, { id: nextId("evt"), at: nowIso(), kind, by: ADMIN, note }]);
}

function refusal(entry: Parsed, item: ConfirmItem): string | null {
  if (entry.item.error) return entry.item.error;
  if (entry.item.meta.ingest_role === "challenge" && !store.settings.benchmark_mode) {
    return "Tài liệu thử thách chỉ nạp được khi bật chế độ benchmark.";
  }
  if (item.on_same_code === "skip" && entry.item.same_code_as) {
    return `Bỏ qua theo lựa chọn: đã có nguồn cùng mã ${item.doc_code ?? ""}`.trim();
  }
  return null;
}

function sourceFrom(entry: Parsed, item: ConfirmItem): Source {
  const at = nowIso();
  const isText = entry.item.format === "text";
  return {
    id: nextId("src"),
    title: item.title,
    doc_code: item.doc_code,
    kind: isText ? "text" : "file",
    format: entry.item.format,
    size: entry.item.size,
    services: item.services,
    audience: item.audience,
    processing: "queued",
    progress: { chunks: 0, labelled: 0, embedded: 0 },
    error: null,
    lifecycle: item.lifecycle,
    version: item.version,
    effective_from: item.effective_from,
    effective_to: item.effective_to,
    approved: item.approved,
    approved_by: item.approved ? ADMIN : null,
    approved_at: item.approved ? at : null,
    chunk_count: entry.item.chunk_count,
    note: item.note,
    created_by: ADMIN,
    created_at: at,
    updated_at: at,
  };
}

function supersede(oldId: string, by: Source): void {
  const found = store.sources.find((source) => source.id === oldId);
  if (!found) return;
  store.sources = store.sources.map((source) =>
    source.id === oldId ? { ...source, lifecycle: "superseded", updated_at: nowIso() } : source,
  );
  addEvent(oldId, "replaced", `Thay bằng "${by.title}"`);
}

function create(entry: Parsed, item: ConfirmItem): Source {
  const created = sourceFrom(entry, item);
  store.sources = [created, ...store.sources];
  if (entry.markdown !== null) store.markdown.set(created.id, entry.markdown);
  if (entry.hash !== "") rememberHash(entry.hash, { id: created.id, title: created.title });
  addEvent(created.id, "uploaded", `Tải lên "${entry.item.name}"`);
  if (item.approved) addEvent(created.id, "approved", "Duyệt khi nạp");
  if (item.supersedes) supersede(item.supersedes, created);
  return created;
}

function confirm(previewId: string, items: readonly ConfirmItem[]): Reply {
  const kept = store.previews.get(previewId);
  if (!isKept(kept)) {
    return { status: 404, body: { detail: "Bản xem trước đã hết hạn, hãy đọc lại tệp." } };
  }
  const checked = items.map((item) => ({ item, entry: kept.parsed.get(item.key) }));
  const unknown = checked.filter(({ entry }) => entry === undefined);
  const known = checked.flatMap(({ item, entry }) => (entry ? [{ item, entry }] : []));
  const skipped = known.flatMap(({ item, entry }) => {
    const reason = refusal(entry, item);
    return reason ? [{ key: item.key, reason }] : [];
  });
  const created = known
    .filter(({ item }) => !skipped.some((skip) => skip.key === item.key))
    .map(({ item, entry }) => create(entry, item));
  const result: ConfirmResult = {
    batch_id: nextId("batch"),
    created,
    skipped: [
      ...skipped,
      ...unknown.map(({ item }) => ({ key: item.key, reason: "Không còn trong bản xem trước." })),
    ],
  };
  return { body: result };
}

export function registerAdd(router: Router): void {
  router.post(`${BASE}/sources/preview`, null, (ctx): Reply => {
    const { inputs = [] } = bodyOf<{ inputs?: PreviewInput[] }>(ctx);
    return { body: preview(inputs) };
  });
  router.post(`${BASE}/sources/confirm`, null, (ctx): Reply => {
    const { preview_id: previewId = "", items = [] } = bodyOf<{
      preview_id?: string;
      items?: ConfirmItem[];
    }>(ctx);
    return confirm(previewId, items);
  });
}
