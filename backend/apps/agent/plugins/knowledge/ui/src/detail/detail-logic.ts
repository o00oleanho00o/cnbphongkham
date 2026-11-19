/** Words and small functions of the source detail (no screen code here). */
import type { Tone } from "../logic";
import type { Audience, Chunk, OutlineNode, Source, SourceEvent } from "../types";

export const MIN_CHUNK_CHARS = 150;
export const MAX_CHUNK_CHARS = 1500;
/** Longer chunk text is cut to this many characters until the person opens it. */
export const COLLAPSED_CHARS = 400;

export const KIND_OPTIONS = [
  { value: "price", label: "Giá" },
  { value: "policy", label: "Chính sách" },
  { value: "procedure", label: "Quy trình" },
  { value: "faq", label: "Hỏi đáp" },
  { value: "info", label: "Thông tin" },
  { value: "internal_script", label: "Kịch bản nội bộ" },
] as const;

const KIND_LABEL: Record<string, string> = Object.fromEntries(KIND_OPTIONS.map((kind) => [kind.value, kind.label]));

export function kindLabel(kind: string): string {
  return KIND_LABEL[kind] ?? kind;
}

const EVENT_LABEL: Record<string, string> = {
  uploaded: "Tải lên",
  approved: "Duyệt",
  unapproved: "Bỏ duyệt",
  reindexed: "Nạp lại",
  edited: "Sửa",
  expired: "Hết hiệu lực",
  error: "Lỗi",
  replaced: "Thay thế",
  restored: "Khôi phục",
};

const EVENT_TONE: Record<string, Tone> = {
  uploaded: "info",
  approved: "success",
  unapproved: "neutral",
  reindexed: "info",
  edited: "neutral",
  expired: "warning",
  error: "danger",
  replaced: "warning",
  restored: "info",
};

export function eventLabel(kind: string): string {
  return EVENT_LABEL[kind] ?? kind;
}

export function eventTone(kind: string): Tone {
  return EVENT_TONE[kind] ?? "neutral";
}

/** A version can be brought back only from a time its text was changed. */
export function canRestore(event: SourceEvent): boolean {
  return event.kind === "edited" || event.kind === "replaced";
}

/** The sentence under a chunk that is too short or too long to be found well; null when its size is fine. */
export function sizeWarning(chars: number): string | null {
  if (chars < MIN_CHUNK_CHARS) return `Đoạn ngắn (${chars} ký tự): dễ thiếu ngữ cảnh, cân nhắc gộp với mục kế bên.`;
  if (chars > MAX_CHUNK_CHARS) return `Đoạn dài (${chars} ký tự): dễ loãng khi tìm, cân nhắc tách thành mục nhỏ.`;
  return null;
}

export function isLong(text: string): boolean {
  return text.length > COLLAPSED_CHARS;
}

export function collapsedText(text: string): string {
  return isLong(text) ? `${text.slice(0, COLLAPSED_CHARS).trimEnd()}...` : text;
}

export function isInternalChunk(chunk: Pick<Chunk, "kind">): boolean {
  return chunk.kind === "internal_script";
}

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/đ/g, "d")
    .toLowerCase();
}

const INTERNAL_HEADING = /kich ban|noi bo|hoa hong|chi tieu|doanh so|script|chot sale|xu ly tu choi/;

/** Titles of sections that read like staff-only material (scripts, commission), for the "make it patient" question. */
export function internalSections(outline: readonly OutlineNode[]): string[] {
  return outline.filter((node) => INTERNAL_HEADING.test(fold(node.title))).map((node) => node.title);
}

export function toggled<T>(items: readonly T[], item: T): T[] {
  return items.includes(item) ? items.filter((other) => other !== item) : [...items, item];
}

export function sameList(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((item) => b.includes(item));
}

/** True when the text on screen differs from the saved one. `null` means nothing was typed. */
export function isDirty(edited: string | null, saved: string): boolean {
  return edited !== null && edited !== saved;
}

export function pageCountOf(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
}

/** The period of a form is wrong when it ends before it starts. */
export function periodError(from: string, to: string): string | null {
  return from !== "" && to !== "" && to < from ? "Ngày kết thúc phải sau ngày bắt đầu." : null;
}

export function splitError(title: string, selected: readonly number[]): string | null {
  if (selected.length === 0) return "Chọn ít nhất một mục trong cây.";
  if (title.trim() === "") return "Đặt tên cho nguồn mới.";
  return null;
}

/** How an outline node is indented: one step per level below the first, at most five. */
export function indentOf(level: number): number {
  return Math.min(Math.max(level - 1, 0), 5);
}

/** The HTTP status carried by a failed call, when it has one. */
export function statusOf(err: unknown): number | null {
  if (typeof err !== "object" || err === null || !("status" in err)) return null;
  return typeof err.status === "number" ? err.status : null;
}

export function canExpire(source: Pick<Source, "lifecycle">): boolean {
  return source.lifecycle === "active" || source.lifecycle === "draft";
}

export function audienceChangeNeedsAsk(from: Audience, to: Audience): boolean {
  return from !== "patient" && to === "patient";
}
