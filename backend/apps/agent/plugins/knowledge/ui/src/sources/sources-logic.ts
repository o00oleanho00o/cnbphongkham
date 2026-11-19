/** The sources tab's pure parts: filters, selection, the refresh rule and the sentences of the bulk actions. */
import type { BulkAction, BulkResult, Source, SourceFormat, SourceList, SourceQuery } from "../types";

export const PAGE_SIZE = 30;
/** How often the list reloads while some source is still being read. */
export const REFRESH_MS = 2000;

export interface Filters {
  q: string;
  processing: string;
  audience: string;
  service: string;
  lifecycle: string;
  unapproved: boolean;
}

export const NO_FILTERS: Filters = {
  q: "",
  processing: "",
  audience: "",
  service: "",
  lifecycle: "",
  unapproved: false,
};

export function hasFilters(filters: Filters): boolean {
  return Object.entries(filters).some(([, value]) => value !== "" && value !== false);
}

/** The values come from `<select>`s offering only valid options, so the casts below only name them. */
export function toQuery(filters: Filters, page: number): SourceQuery {
  return {
    q: filters.q.trim() || undefined,
    processing: (filters.processing || undefined) as SourceQuery["processing"],
    audience: (filters.audience || undefined) as SourceQuery["audience"],
    service: filters.service || undefined,
    lifecycle: (filters.lifecycle || undefined) as SourceQuery["lifecycle"],
    approved: filters.unapproved ? false : undefined,
    page: page > 1 ? page : undefined,
  };
}

/** True while some source is queued or being processed: the list should keep reloading. */
export function needsRefresh(list: SourceList | null): boolean {
  if (!list) return false;
  const waiting = (source: Source) => source.processing === "queued" || source.processing === "processing";
  return list.summary.processing > 0 || list.items.some(waiting);
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}

/** "1-30 / 64 nguồn". */
export function rangeText(list: Pick<SourceList, "total" | "page" | "page_size">, shown: number): string {
  if (list.total === 0) return "0 nguồn";
  const first = (list.page - 1) * list.page_size + 1;
  return `${first}-${first + shown - 1} / ${list.total} nguồn`;
}

// -- selection ----------------------------------------------------------------------------------------------

export function toggleId(selected: readonly string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id];
}

export function allSelected(selected: readonly string[], pageIds: readonly string[]): boolean {
  return pageIds.length > 0 && pageIds.every((id) => selected.includes(id));
}

/** Select-all on the page: everything when something is missing, nothing when all are in. */
export function toggleAll(selected: readonly string[], pageIds: readonly string[]): string[] {
  if (allSelected(selected, pageIds)) return selected.filter((id) => !pageIds.includes(id));
  return [...selected, ...pageIds.filter((id) => !selected.includes(id))];
}

/** Keeps the ids still on screen (after a reload, a filter or a page change). */
export function pruneSelection(selected: readonly string[], pageIds: readonly string[]): string[] {
  const kept = selected.filter((id) => pageIds.includes(id));
  return kept.length === selected.length ? [...selected] : kept;
}

// -- words --------------------------------------------------------------------------------------------------

const FORMAT_LABEL: Record<SourceFormat, string> = {
  md: "Markdown",
  txt: "TXT",
  docx: "Word",
  xlsx: "Excel",
  pdf: "PDF",
  text: "Văn bản",
};

/** "Tệp" / "Văn bản gõ tay" with the format under it. */
export function kindText(source: Pick<Source, "kind" | "format">): { kind: string; format: string } {
  return {
    kind: source.kind === "text" ? "Văn bản gõ tay" : "Tệp",
    format: FORMAT_LABEL[source.format],
  };
}

/** "Quản trị, 12/10/2026" is built by the caller; this is the who of the approval column. */
export function approvalWho(source: Pick<Source, "approved" | "approved_by">): string {
  if (!source.approved) return "";
  return source.approved_by ?? "";
}

const UNAPPROVED_WARNING = /^\d+ nguồn chưa duyệt/;

/** The strip of warnings without the "N nguồn chưa duyệt" one: the page shows that as a filter button. */
export function visibleWarnings(warnings: readonly string[]): string[] {
  return warnings.filter((text) => !UNAPPROVED_WARNING.test(text));
}

export function chunksOf(sources: readonly Source[]): number {
  return sources.reduce((sum, source) => sum + source.chunk_count, 0);
}

/** The body of the delete question: how many chunks go and what the agent loses. */
export function deleteText(sources: readonly Source[]): string {
  const chunks = chunksOf(sources);
  return `Xóa ${sources.length} nguồn sẽ mất ${chunks} đoạn. Agent sẽ không còn dẫn chứng từ ${
    sources.length === 1 ? "nguồn này" : "các nguồn này"
  }. Không hoàn tác được.`;
}

export type BulkKind = "approve" | "unapprove" | "audience-patient" | "audience-staff" | "reindex" | "delete";

const BULK_DONE: Record<BulkKind, string> = {
  approve: "Đã duyệt",
  unapprove: "Đã bỏ duyệt",
  "audience-patient": "Đã đặt đối tượng Bệnh nhân cho",
  "audience-staff": "Đã đặt đối tượng Nội bộ cho",
  reindex: "Đã đưa vào hàng đợi nạp lại",
  delete: "Đã xóa",
};

const BULK_ACTION: Record<BulkKind, BulkAction> = {
  approve: { action: "approve" },
  unapprove: { action: "unapprove" },
  "audience-patient": { action: "audience", audience: "patient" },
  "audience-staff": { action: "audience", audience: "staff" },
  reindex: { action: "reindex" },
  delete: { action: "delete" },
};

export function bulkActionOf(kind: BulkKind): BulkAction {
  return BULK_ACTION[kind];
}

export function bulkDoneText(kind: BulkKind, done: number): string {
  return `${BULK_DONE[kind]} ${done} nguồn`;
}

/** One line per failed row, with the source's title when it is still on screen. */
export function failureLines(result: BulkResult, sources: readonly Source[]): string[] {
  const titles = new Map(sources.map((source) => [source.id, source.title]));
  return result.failed.map((row) => `${titles.get(row.id) ?? row.id}: ${row.message}`);
}
