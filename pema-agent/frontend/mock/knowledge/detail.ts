// Routes of the fake knowledge store: the detail of one source (structure, split, chunks, history, restore).
// `/sources/{id}` itself and reindex/approve/expire belong to sources.ts. Every pattern here has more than one
// segment after `/sources/`, so none of them can match `bulk`, `preview` or `confirm`.
import type {
  Chunk,
  ChunkList,
  Source,
  SourceEvent,
  SourceStructure,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { type Reply, type Router, bodyOf, clampInt } from "../core";
import { bumpVersion, chunksOf, generateMarkdown, outlineOf, takeSections } from "./markdown";
import { nextId, nowIso, store } from "./store";

const BASE = "/v1/plugins/knowledge";
const PAGE_SIZE = 20;
const KINDS = ["price", "policy", "procedure", "faq", "info", "internal_script"];
const ADMIN = "Quản trị";
const NOT_FOUND: Reply = { status: 404, body: { detail: "Không tìm thấy nguồn này." } };

interface ChunkOverride {
  services?: string[];
  kind?: string;
}

/** Labels a person changed by hand, kept across edits of the text (chunk ids are stable). */
const overrides = new Map<string, ChunkOverride>();
/** Event id -> the Markdown that version had, for "Khôi phục bản này". */
const snapshots = new Map<string, string>();

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/g, "d")
    .toLowerCase();
}

const KIND_RULES: [RegExp, string][] = [
  [/kich ban|noi bo/, "internal_script"],
  [/gia|phi/, "price"],
  [/quy trinh|truoc khi|sau khi|cac buoc/, "procedure"],
  [/chinh sach|luu y|bao hanh|hoan tien/, "policy"],
  [/cau hoi|hoi dap|faq/, "faq"],
];

function kindOf(path: string): string {
  const heading = fold(path.split(" > ").at(-1) ?? "");
  return KIND_RULES.find(([pattern]) => pattern.test(heading))?.[1] ?? "info";
}

function find(id: string | undefined): Source | undefined {
  return store.sources.find((source) => source.id === id);
}

function save(next: Source): Source {
  store.sources = store.sources.map((source) => (source.id === next.id ? next : source));
  return next;
}

function addEvent(sourceId: string, kind: string, note: string): SourceEvent {
  const event: SourceEvent = { id: nextId("evt"), at: nowIso(), kind, by: ADMIN, note };
  store.events.set(sourceId, [event, ...(store.events.get(sourceId) ?? [])]);
  return event;
}

/** The text of a source; made up (and kept) the first time it is asked for. A source that failed has none. */
function markdownOf(source: Source): string {
  const known = store.markdown.get(source.id);
  if (known !== undefined) return known;
  if (source.processing === "error" && source.chunk_count === 0) return "";
  const made = generateMarkdown(source.title);
  store.markdown.set(source.id, made);
  const chunks = chunksOf(source.id, made).length;
  save({
    ...source,
    chunk_count: chunks,
    progress: {
      chunks,
      labelled: Math.min(source.progress.labelled, chunks),
      embedded: Math.min(source.progress.embedded, chunks),
    },
  });
  return made;
}

/** The new text is what the source is now: chunk counts reset and the reader runs again. */
function withMarkdown(source: Source, markdown: string): Source {
  store.markdown.set(source.id, markdown);
  const chunks = chunksOf(source.id, markdown).length;
  return save({
    ...source,
    chunk_count: chunks,
    progress: { chunks, labelled: 0, embedded: 0 },
    processing: "queued",
    error: null,
    updated_at: nowIso(),
  });
}

function chunkViews(source: Source, markdown: string): Chunk[] {
  return chunksOf(source.id, markdown).map((draft) => {
    const own = overrides.get(draft.id) ?? {};
    return {
      id: draft.id,
      ordinal: draft.ordinal,
      path: draft.path,
      text: draft.text,
      chars: draft.chars,
      services: own.services ?? source.services,
      kind: own.kind ?? kindOf(draft.path),
      embedded: draft.ordinal < source.progress.embedded,
    };
  });
}

function eventsOf(source: Source): SourceEvent[] {
  const known = store.events.get(source.id);
  if (known && known.length > 0) return known;
  const uploaded: SourceEvent = {
    id: nextId("evt"),
    at: source.created_at,
    kind: "uploaded",
    by: source.created_by,
    note: `Tải lên "${source.title}"`,
  };
  store.events.set(source.id, [uploaded]);
  return [uploaded];
}

function split(source: Source, sections: readonly number[], title: string): Reply {
  const { kept, moved } = takeSections(markdownOf(source), sections);
  if (moved === "") return { status: 422, body: { detail: "Các mục đã chọn không còn trong bản dựng." } };
  const made = nowIso();
  const draft: Source = {
    ...source,
    id: nextId("src"),
    title,
    doc_code: null,
    version: "1.0",
    audience: "staff",
    approved: false,
    approved_by: null,
    approved_at: null,
    lifecycle: "active",
    note: `Tách từ "${source.title}"`,
    created_by: ADMIN,
    created_at: made,
    updated_at: made,
  };
  store.sources = [draft, ...store.sources];
  const created = withMarkdown(draft, `# ${title}\n\n${moved}`);
  withMarkdown(find(source.id) ?? source, kept);
  addEvent(source.id, "edited", `Tách ${sections.length} mục sang nguồn mới "${title}"`);
  addEvent(created.id, "uploaded", `Tách từ "${source.title}"`);
  return { status: 201, body: created };
}

function restore(source: Source, eventId: string | undefined): Reply {
  const event = eventsOf(source).find((candidate) => candidate.id === eventId);
  if (!event || !["edited", "replaced"].includes(event.kind)) {
    return { status: 409, body: { detail: "Chỉ khôi phục được từ một lần sửa hoặc thay thế." } };
  }
  const restored = withMarkdown(source, snapshots.get(event.id) ?? generateMarkdown(source.title));
  const version = bumpVersion(restored.version);
  addEvent(source.id, "restored", `Khôi phục từ bản ngày ${event.at.slice(0, 10)}, thành phiên bản ${version}`);
  return { body: save({ ...restored, version }) };
}

function updateChunk(chunkId: string, patch: ChunkOverride): Reply {
  const owner = /^(.*)-c\d+$/.exec(chunkId)?.[1];
  const source = find(owner);
  if (!source) return { status: 404, body: { detail: "Không tìm thấy đoạn này." } };
  if (patch.kind !== undefined && !KINDS.includes(patch.kind)) {
    return { status: 422, body: { detail: "Loại đoạn không hợp lệ." } };
  }
  overrides.set(chunkId, {
    ...overrides.get(chunkId),
    ...(patch.services === undefined ? {} : { services: patch.services }),
    ...(patch.kind === undefined ? {} : { kind: patch.kind }),
  });
  save({ ...source, updated_at: nowIso() });
  return { status: 204 };
}

export function registerDetail(router: Router): void {
  router.get(`${BASE}/sources/{id}/structure`, null, (ctx): Reply => {
    const source = find(ctx.params.id);
    if (!source) return NOT_FOUND;
    const markdown = markdownOf(source);
    const body: SourceStructure = { markdown, outline: outlineOf(markdown) };
    return { body };
  });

  router.put(`${BASE}/sources/{id}/structure`, null, (ctx): Reply => {
    const source = find(ctx.params.id);
    if (!source) return NOT_FOUND;
    const { markdown } = bodyOf<{ markdown?: string }>(ctx);
    if (typeof markdown !== "string") return { status: 422, body: { detail: "Thiếu nội dung bản dựng." } };
    const saved = withMarkdown(source, markdown);
    const event = addEvent(source.id, "edited", "Sửa bản dựng cấu trúc và nạp lại");
    snapshots.set(event.id, markdown);
    return { body: saved };
  });

  router.post(`${BASE}/sources/{id}/split`, null, (ctx): Reply => {
    const source = find(ctx.params.id);
    if (!source) return NOT_FOUND;
    const { sections, title } = bodyOf<{ sections?: number[]; title?: string }>(ctx);
    const name = (title ?? "").trim();
    if (!Array.isArray(sections) || sections.length === 0 || name === "") {
      return { status: 422, body: { detail: "Chọn ít nhất một mục và đặt tên cho nguồn mới." } };
    }
    return split(source, sections, name);
  });

  router.get(`${BASE}/sources/{id}/chunks`, null, (ctx): Reply => {
    const source = find(ctx.params.id);
    if (!source) return NOT_FOUND;
    const wanted = fold((ctx.query.get("q") ?? "").trim());
    const all = chunkViews(find(source.id) ?? source, markdownOf(source)).filter(
      (chunk) => wanted === "" || fold(`${chunk.path} ${chunk.text}`).includes(wanted),
    );
    const page = clampInt(ctx.query.get("page"), 1, 1, Math.max(1, Math.ceil(all.length / PAGE_SIZE)));
    const body: ChunkList = {
      items: all.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
      total: all.length,
      page,
      page_size: PAGE_SIZE,
    };
    return { body };
  });

  router.patch(`${BASE}/chunks/{id}`, null, (ctx): Reply => updateChunk(ctx.params.id ?? "", bodyOf<ChunkOverride>(ctx)));

  router.get(`${BASE}/sources/{id}/events`, null, (ctx): Reply => {
    const source = find(ctx.params.id);
    if (!source) return NOT_FOUND;
    return { body: eventsOf(source).toSorted((a, b) => b.at.localeCompare(a.at)) };
  });

  router.post(`${BASE}/sources/{id}/restore`, null, (ctx): Reply => {
    const source = find(ctx.params.id);
    if (!source) return NOT_FOUND;
    return restore(source, bodyOf<{ event?: string }>(ctx).event);
  });
}
