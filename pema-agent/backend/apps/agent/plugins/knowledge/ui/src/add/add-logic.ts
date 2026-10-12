/** The rules of the add-a-source flow with no screen in them: what may be sent, what a file starts as, what is added. */
import {
  FILE_EXTENSIONS,
  MAX_FILE_BYTES,
  MAX_TEXT_CHARS,
  formatSize,
  hasExtension,
  todayIso,
} from "../logic";
import type {
  Audience,
  ConfirmItem,
  Lifecycle,
  PreviewItem,
  PreviewMeta,
  PreviewWarning,
} from "../types";
import { emptyMeta } from "./frontmatter";

export const MAX_FOLDER_FILES = 200;
export const BATCH_FILES = 10;
/** Raw bytes per preview call: base64 grows a third, and the gateway limits a request body. */
export const BATCH_BYTES = 8 * 1024 * 1024;

export type Way = "files" | "text" | "folder";

export interface FileInfo {
  name: string;
  size: number;
}

export interface Rejection {
  name: string;
  reason: string;
}

export function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

const ACCEPTED = FILE_EXTENSIONS.join(" ");

/** The reason a file must not be sent, or null. Checked the moment the file is picked. */
export function validateFile({ name, size }: FileInfo): string | null {
  if (!hasExtension(name)) {
    return `Định dạng ${extensionOf(name) || "không rõ"} chưa hỗ trợ (chỉ nhận ${ACCEPTED}).`;
  }
  if (size === 0) return "Tệp rỗng.";
  if (size > MAX_FILE_BYTES) {
    return `Tệp nặng ${formatSize(size)}, tối đa ${formatSize(MAX_FILE_BYTES)}.`;
  }
  return null;
}

export function validateText(title: string, text: string): string | null {
  if (title.trim() === "") return "Nhập tiêu đề.";
  if (text.trim() === "") return "Nhập nội dung.";
  if (text.length > MAX_TEXT_CHARS) {
    return `Nội dung dài ${text.length.toLocaleString("vi-VN")} ký tự, tối đa ${MAX_TEXT_CHARS.toLocaleString("vi-VN")}.`;
  }
  return null;
}

export interface FolderPlan<T extends FileInfo> {
  accepted: T[];
  rejected: Rejection[];
  /** Files of another type (or hidden), left out without a word each. */
  ignoredType: number;
  /** Files beyond the cap. */
  ignoredOverCap: number;
}

/** Keeps the allowed files of a folder (up to the cap); the rest is counted so the person is told. */
export function planFolder<T extends FileInfo>(entries: readonly T[]): FolderPlan<T> {
  const allowed = entries.filter((entry) => hasExtension(entry.name) && !entry.name.startsWith("."));
  const checked = allowed.map((entry) => ({ entry, reason: validateFile(entry) }));
  const sendable = checked.filter((item) => item.reason === null).map((item) => item.entry);
  return {
    accepted: sendable.slice(0, MAX_FOLDER_FILES),
    rejected: checked.flatMap((item) => (item.reason ? [{ name: item.entry.name, reason: item.reason }] : [])),
    ignoredType: entries.length - allowed.length,
    ignoredOverCap: Math.max(0, sendable.length - MAX_FOLDER_FILES),
  };
}

/** "Bỏ qua 14 tệp không đúng định dạng và 3 tệp vượt giới hạn 200 tệp", or an empty text. */
export function ignoredText(plan: Pick<FolderPlan<FileInfo>, "ignoredType" | "ignoredOverCap">): string {
  const parts = [
    plan.ignoredType > 0 ? `${plan.ignoredType} tệp không đúng định dạng` : "",
    plan.ignoredOverCap > 0 ? `${plan.ignoredOverCap} tệp vượt giới hạn ${MAX_FOLDER_FILES} tệp` : "",
  ].filter((part) => part !== "");
  return parts.length > 0 ? `Bỏ qua ${parts.join(" và ")}.` : "";
}

/** Stable for the same file picked again: the path when a folder gave one, else name + size + time. */
export function fileKey(name: string, size: number, modified: number, path = ""): string {
  return `${path || name}|${size}|${modified}`;
}

/** Splits into calls of at most `maxCount` items and `maxBytes` of weight; one heavy item goes alone. */
export function batchBySize<T>(
  items: readonly T[],
  weight: (item: T) => number,
  maxCount = BATCH_FILES,
  maxBytes = BATCH_BYTES,
): T[][] {
  return items.reduce<{ batches: T[][]; bytes: number }>(
    (state, item) => {
      const last = state.batches[state.batches.length - 1];
      if (last !== undefined && last.length < maxCount && state.bytes + weight(item) <= maxBytes) {
        return { batches: [...state.batches.slice(0, -1), [...last, item]], bytes: state.bytes + weight(item) };
      }
      return { batches: [...state.batches, [item]], bytes: weight(item) };
    },
    { batches: [], bytes: 0 },
  ).batches;
}

/** `FileReader.readAsDataURL` gives `data:<type>;base64,<data>`; the call wants the data only. */
export function base64FromDataUrl(url: string): string {
  const comma = url.indexOf(",");
  return comma < 0 ? "" : url.slice(comma + 1);
}

export function nameWithoutExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

// -- step 2: what a file starts as --------------------------------------------------------------------------

export interface Draft {
  key: string;
  title: string;
  docCode: string;
  audience: Audience;
  approved: boolean;
  /** Service codes; empty means "recognise them". */
  services: string[];
  from: string;
  to: string;
  /** Id of the source this one replaces; empty for none. */
  supersedes: string;
  note: string;
  lifecycle: Lifecycle;
  version: string;
  action: "add" | "skip";
}

/** The YAML head decides; without one the file starts internal and not approved (the safe default). */
export function audienceDefaults(audience: Audience | null): { audience: Audience; approved: boolean } {
  if (audience === "patient") return { audience: "patient", approved: true };
  if (audience === "staff") return { audience: "staff", approved: true };
  return { audience: "staff", approved: false };
}

/** What the server read first, then what this browser read from the same head. */
export function mergeMeta(server: PreviewMeta, local: PreviewMeta | undefined): PreviewMeta {
  const fallback = local ?? emptyMeta();
  return {
    doc_code: server.doc_code ?? fallback.doc_code,
    title: server.title ?? fallback.title,
    tenant_id: server.tenant_id ?? fallback.tenant_id,
    version: server.version ?? fallback.version,
    lifecycle: server.lifecycle ?? fallback.lifecycle,
    effective_from: server.effective_from ?? fallback.effective_from,
    effective_to: server.effective_to ?? fallback.effective_to,
    audience: server.audience ?? fallback.audience,
    ingest_role: server.ingest_role ?? fallback.ingest_role,
  };
}

export function defaultDraft(item: PreviewItem, today: string = todayIso()): Draft {
  const { meta } = item;
  return {
    key: item.key,
    title: meta.title ?? nameWithoutExtension(item.name),
    docCode: meta.doc_code ?? "",
    ...audienceDefaults(meta.audience),
    services: [],
    from: meta.effective_from ?? today,
    to: meta.effective_to ?? "",
    supersedes: "",
    note: "",
    lifecycle: meta.lifecycle ?? "active",
    version: meta.version ?? "",
    action: item.same_content_as ? "skip" : "add",
  };
}

export function draftProblems(draft: Draft): { title?: string; to?: string } {
  return {
    ...(draft.title.trim() === "" ? { title: "Nhập tên hiển thị." } : {}),
    ...(draft.to !== "" && draft.from !== "" && draft.to < draft.from
      ? { to: "Ngày hết hạn phải sau ngày bắt đầu." }
      : {}),
  };
}

export function hasProblems(draft: Draft): boolean {
  return Object.keys(draftProblems(draft)).length > 0;
}

/** Why a file cannot be added at all, or null. Such a file is listed and left out; the others go on. */
export function refusalOf(item: PreviewItem, benchmark: boolean): string | null {
  if (item.error) return item.error;
  if (item.meta.ingest_role === "challenge" && !benchmark) {
    return "Tài liệu thử thách (ingest_role: challenge) chỉ nạp được khi bật chế độ benchmark trong Cài đặt.";
  }
  const tenant = item.warnings.find((warning) => warning.code === "tenant" && warning.level === "error");
  return tenant ? tenant.text : null;
}

const PATIENT_RISK_CODES = ["internal_script", "personal_data"];

/** The warnings that matter when a file is shown to patients. */
export function patientRisks(item: PreviewItem): PreviewWarning[] {
  return item.warnings.filter((warning) => PATIENT_RISK_CODES.includes(warning.code));
}

export interface Entry {
  item: PreviewItem;
  draft: Draft;
}

/** What goes to `confirm`: files to add, and the skipped ones that clash by code (the server says why it left them). */
export function toConfirmItems(entries: readonly Entry[]): ConfirmItem[] {
  return entries
    .filter(({ item, draft }) => draft.action === "add" || item.same_code_as !== null)
    .map(({ item, draft }) => ({
      key: item.key,
      title: draft.title.trim(),
      doc_code: draft.docCode.trim() || null,
      audience: draft.audience,
      approved: draft.approved,
      services: draft.services,
      lifecycle: draft.lifecycle,
      version: draft.version.trim() || null,
      effective_from: draft.from || null,
      effective_to: draft.to || null,
      supersedes: draft.supersedes || null,
      note: draft.note.trim(),
      on_same_code: draft.action === "skip" ? "skip" : "version",
    }));
}

export interface Summary {
  sources: number;
  chunks: number;
  warnings: number;
}

/** "Sẽ nạp N nguồn, ~M đoạn, K cảnh báo": only the files to add count. */
export function summarise(entries: readonly Entry[]): Summary {
  const added = entries.filter(({ draft }) => draft.action === "add");
  return {
    sources: added.length,
    chunks: added.reduce((sum, { item }) => sum + item.chunk_count, 0),
    warnings: added.reduce((sum, { item }) => sum + item.warnings.filter((w) => w.level !== "info").length, 0),
  };
}

export function summaryText(summary: Summary): string {
  return `Sẽ nạp ${summary.sources} nguồn, ~${summary.chunks} đoạn, ${summary.warnings} cảnh báo`;
}

export interface CodeGroup {
  /** Shared `doc_code`, or null for a file that stands alone. */
  code: string | null;
  entries: Entry[];
}

/** Files that share a `doc_code` sit together, oldest effective date first, so versions are read side by side. */
export function groupByCode(entries: readonly Entry[]): CodeGroup[] {
  const codes = entries.map(({ draft }) => draft.docCode.trim());
  const shared = (code: string) => code !== "" && codes.filter((other) => other === code).length > 1;
  const order = codes.filter((code, index) => shared(code) && codes.indexOf(code) === index);
  const alone = entries.filter((_, index) => !shared(codes[index] ?? ""));
  const grouped = order.map((code) => ({
    code,
    entries: entries
      .filter(({ draft }) => draft.docCode.trim() === code)
      .toSorted((a, b) => a.draft.from.localeCompare(b.draft.from)),
  }));
  return [...grouped, ...alone.map((entry) => ({ code: null, entries: [entry] }))];
}

/** The replacement choice lists sources in use by title and version. */
export function replaceLabel(title: string, version: string | null): string {
  return version ? `${title} (v${version})` : title;
}

export interface PreviewGroup {
  previewId: string;
  items: ConfirmItem[];
}

/** `confirm` takes one preview id, and a big batch is read in several calls: send one confirm per call's files. */
export function splitByPreview(items: readonly ConfirmItem[], previewIds: Readonly<Record<string, string>>): PreviewGroup[] {
  return items.reduce<PreviewGroup[]>((groups, item) => {
    const previewId = previewIds[item.key] ?? "";
    const found = groups.find((group) => group.previewId === previewId);
    if (!found) return [...groups, { previewId, items: [item] }];
    return groups.map((group) => (group === found ? { ...group, items: [...group.items, item] } : group));
  }, []);
}

/** "Đang đọc 12/22 tệp" while the files go out in groups. */
export function readingText(done: number, total: number): string {
  return `Đang đọc ${done}/${total} tệp`;
}

/** A select's value as an audience; empty (or anything else) means "leave as it is". */
export function audienceFromValue(value: string): Audience | "" {
  return value === "patient" || value === "staff" ? value : "";
}

export function approvedFromValue(value: string): "" | "yes" | "no" {
  return value === "yes" || value === "no" ? value : "";
}
