// Routes of the fake knowledge store: the list of sources, one source, bulk changes and the status line.
// `preview` and `confirm` (POST, owned by add.ts) never clash with these: no POST route here has a lone `{id}`.
import { type Ctx, type Reply, type Router, bodyOf } from "../core";
import type {
  BulkAction,
  BulkResult,
  Source,
  SourceList,
  SourcePatch,
  SourceSummary,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { nextId, nowIso, store } from "./store";

const PAGE_SIZE = 30;
const ADMIN = "Quản trị";
const NOT_FOUND = "Không tìm thấy nguồn này.";

/** Lower case without accents, so "nam" finds "Nám". */
function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .toLowerCase();
}

function notFound(): Reply {
  return { status: 404, body: { detail: NOT_FOUND } };
}

function record(id: string, kind: string, note = ""): void {
  const events = store.events.get(id) ?? [];
  store.events.set(id, [...events, { id: nextId("evt"), at: nowIso(), kind, by: ADMIN, note }]);
}

function replace(id: string, change: (source: Source) => Source): Source | null {
  const found = store.sources.find((item) => item.id === id);
  if (!found) return null;
  const next = change(found);
  store.sources = store.sources.map((item) => (item.id === id ? next : item));
  return next;
}

const step = (chunks: number) => Math.max(1, Math.ceil(chunks / 4));

/** One tick of the background work: queued -> split -> labelled -> embedded (only with a key) -> ready. */
function advance(source: Source): Source {
  if (source.processing === "queued") {
    const chunks = source.progress.chunks || source.chunk_count || 10;
    return { ...source, processing: "processing", progress: { chunks, labelled: 0, embedded: 0 } };
  }
  if (source.processing !== "processing") return source;
  const { chunks, labelled, embedded } = source.progress;
  const hasKey = store.settings.embedding.has_key;
  const labelling = labelled < chunks;
  const embedding = !labelling && hasKey && embedded < chunks;
  const progress = {
    chunks,
    labelled: labelling ? Math.min(chunks, labelled + step(chunks)) : labelled,
    embedded: embedding ? Math.min(chunks, embedded + step(chunks)) : embedded,
  };
  const finished = progress.labelled === chunks && (!hasKey || progress.embedded === chunks);
  return finished
    ? { ...source, progress, processing: "ready", chunk_count: chunks, updated_at: nowIso() }
    : { ...source, progress };
}

function summaryOf(sources: readonly Source[]): SourceSummary {
  const chunks = sources.reduce((sum, item) => sum + item.chunk_count, 0);
  const embedded = sources.reduce((sum, item) => sum + item.progress.embedded, 0);
  return {
    ready: sources.filter((item) => item.processing === "ready").length,
    chunks,
    embedded_percent: chunks === 0 ? 0 : Math.min(100, Math.round((embedded / chunks) * 100)),
    errors: sources.filter((item) => item.processing === "error").length,
    unapproved: sources.filter((item) => !item.approved).length,
    processing: sources.filter((item) => item.processing === "queued" || item.processing === "processing").length,
  };
}

function warningsOf(summary: SourceSummary): string[] {
  return [
    ...(store.settings.embedding.has_key ? [] : ["Embedding chưa kết nối: đang tìm bằng từ khóa"]),
    ...(summary.unapproved > 0 ? [`${summary.unapproved} nguồn chưa duyệt`] : []),
    ...(summary.errors > 0 ? [`${summary.errors} nguồn lỗi`] : []),
  ];
}

function filtered(query: URLSearchParams): Source[] {
  const text = fold(query.get("q") ?? "");
  const processing = query.get("processing");
  const audience = query.get("audience");
  const service = query.get("service");
  const lifecycle = query.get("lifecycle");
  const approved = query.get("approved");
  return store.sources.filter(
    (item) =>
      (text === "" || fold(`${item.title} ${item.doc_code ?? ""}`).includes(text)) &&
      (!processing || item.processing === processing) &&
      (!audience || item.audience === audience) &&
      (!service || item.services.includes(service)) &&
      (!lifecycle || item.lifecycle === lifecycle) &&
      (approved === null || item.approved === (approved === "true")),
  );
}

function list(ctx: Ctx): Reply {
  store.sources = store.sources.map(advance);
  const page = Math.max(1, Number.parseInt(ctx.query.get("page") ?? "1", 10) || 1);
  const found = filtered(ctx.query);
  const summary = summaryOf(store.sources);
  const body: SourceList = {
    items: found.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    total: found.length,
    page,
    page_size: PAGE_SIZE,
    summary,
    warnings: warningsOf(summary),
  };
  return { body };
}

type Change = (source: Source) => { source: Source; event: [string, string] } | { error: string };

const approve: Change = (source) => {
  if (source.processing === "error") return { error: "Nguồn đang lỗi: nạp lại trước khi duyệt." };
  if (source.processing !== "ready") return { error: "Nguồn đang được xử lý: chờ xong rồi duyệt." };
  const at = nowIso();
  return { source: { ...source, approved: true, approved_by: ADMIN, approved_at: at, updated_at: at }, event: ["approved", ""] };
};

const unapprove: Change = (source) => ({
  source: { ...source, approved: false, approved_by: null, approved_at: null, updated_at: nowIso() },
  event: ["unapproved", ""],
});

const reindex: Change = (source) => ({
  source: {
    ...source,
    processing: "queued",
    error: null,
    progress: { chunks: 0, labelled: 0, embedded: 0 },
    updated_at: nowIso(),
  },
  event: ["reindexed", ""],
});

const expire: Change = (source) => ({
  source: { ...source, lifecycle: "expired", effective_to: nowIso().slice(0, 10), updated_at: nowIso() },
  event: ["expired", ""],
});

const audienceTo =
  (audience: "patient" | "staff"): Change =>
  (source) => ({
    source: { ...source, audience, updated_at: nowIso() },
    event: ["edited", `Đối tượng: ${audience === "patient" ? "Bệnh nhân" : "Nội bộ"}`],
  });

/** Applies a change to one source and records its event; returns the sentence of a refusal as `error`. */
function apply(id: string, change: Change): { source: Source } | { error: string } {
  const found = store.sources.find((item) => item.id === id);
  if (!found) return { error: NOT_FOUND };
  const result = change(found);
  if ("error" in result) return result;
  replace(id, () => result.source);
  record(id, result.event[0], result.event[1]);
  return { source: result.source };
}

function remove(id: string): { error: string } | null {
  if (!store.sources.some((item) => item.id === id)) return { error: NOT_FOUND };
  store.sources = store.sources.filter((item) => item.id !== id);
  store.markdown.delete(id);
  store.events.delete(id);
  return null;
}

function changeOf(action: BulkAction): Change | null {
  if (action.action === "approve") return approve;
  if (action.action === "unapprove") return unapprove;
  if (action.action === "reindex") return reindex;
  if (action.action === "audience") return audienceTo(action.audience);
  return null;
}

function bulk(ctx: Ctx): Reply {
  const body = bodyOf<{ ids?: string[] } & BulkAction>(ctx);
  const ids = body.ids ?? [];
  const change = changeOf(body);
  const results = ids.map((id) => ({ id, result: change ? apply(id, change) : remove(id) }));
  const failed = results.flatMap(({ id, result }) => (result && "error" in result ? [{ id, message: result.error }] : []));
  const out: BulkResult = { done: ids.length - failed.length, failed };
  return { body: out };
}

function single(change: Change) {
  return (ctx: Ctx): Reply => {
    const result = apply(ctx.params.id ?? "", change);
    if (!("error" in result)) return { body: result.source };
    return { status: result.error === NOT_FOUND ? 404 : 409, body: { detail: result.error } };
  };
}

function patch(ctx: Ctx): Reply {
  const body = bodyOf<SourcePatch>(ctx);
  const next = replace(ctx.params.id ?? "", (source) => ({ ...source, ...body, updated_at: nowIso() }));
  if (!next) return notFound();
  record(next.id, "edited", Object.keys(body).join(", "));
  return { body: next };
}

export function registerSources(router: Router): void {
  const base = "/v1/plugins/knowledge";
  router.get(`${base}/status`, null, (): Reply => {
    const summary = summaryOf(store.sources);
    return {
      body: {
        embedding_connected: store.settings.embedding.has_key,
        embedding_model: store.settings.embedding.has_key ? store.settings.embedding.model : null,
        queue: summary.processing,
        warnings: warningsOf(summary),
      },
    };
  });
  router.get(`${base}/sources`, null, (ctx): Reply => list(ctx));
  // `bulk` goes before every `{id}` route: the router takes the first pattern that matches.
  router.post(`${base}/sources/bulk`, null, (ctx): Reply => bulk(ctx));
  router.get(`${base}/sources/{id}`, null, (ctx): Reply => {
    const found = store.sources.find((item) => item.id === ctx.params.id);
    return found ? { body: found } : notFound();
  });
  router.patch(`${base}/sources/{id}`, null, (ctx): Reply => patch(ctx));
  router.delete(`${base}/sources/{id}`, null, (ctx): Reply => {
    const id = ctx.params.id ?? "";
    return remove(id) ? notFound() : { body: { deleted: id } };
  });
  router.post(`${base}/sources/{id}/reindex`, null, single(reindex));
  router.post(`${base}/sources/{id}/approve`, null, single(approve));
  router.post(`${base}/sources/{id}/unapprove`, null, single(unapprove));
  router.post(`${base}/sources/{id}/expire`, null, single(expire));
}
