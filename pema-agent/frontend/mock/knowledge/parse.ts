// A believable reader for the fake knowledge store's preview: YAML head, outline, chunks and warnings of a text, and a
// guess from the file name for files the browser sends as base64 (pdf, docx, xlsx). Pure apart from reading the store
// (same code / same title) and the hashes of what was added before. The plugin's own YAML reader lives in its `src`;
// this one is written again on purpose (the mock does not import plugin code).
import { createHash } from "node:crypto";

import type {
  Audience,
  Lifecycle,
  OutlineNode,
  PreviewInput,
  PreviewItem,
  PreviewMeta,
  PreviewWarning,
  SourceFormat,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { store } from "./store";

const TENANT = "DEMO-PEMA";
const MIN_CHUNK_CHARS = 150;
const CHUNK_CHARS = 1500;
const LIFECYCLES: readonly Lifecycle[] = ["active", "draft", "superseded", "adversarial"];
const AUDIENCES: readonly Audience[] = ["patient", "staff"];
const ROLES = ["kb", "challenge"] as const;

/** Text hash -> the source added with it, to say "the same content is already there". */
const hashes = new Map<string, { id: string; title: string }>();

export function rememberHash(hash: string, source: { id: string; title: string }): void {
  hashes.set(hash, source);
}

export function hashOf(text: string): string {
  return createHash("sha1").update(text.replace(/\s+/g, " ").trim()).digest("hex");
}

export function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").toLowerCase();
}

// -- the YAML head -------------------------------------------------------------------------------------------

function scalar(raw: string): string | null {
  const value = raw.trim();
  const quoted = /^(["'])(.*)\1$/.exec(value);
  if (quoted) return quoted[2] ?? "";
  const bare = value.replace(/\s+#.*$/, "").trim();
  return bare === "" || bare === "null" || bare === "~" ? null : bare;
}

function oneOf<T extends string>(allowed: readonly T[], value: string | null): T | null {
  return allowed.find((option) => option === value) ?? null;
}

function dateOf(value: string | null): string | null {
  return value !== null && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : null;
}

export function emptyMeta(): PreviewMeta {
  return {
    doc_code: null,
    title: null,
    tenant_id: null,
    version: null,
    lifecycle: null,
    effective_from: null,
    effective_to: null,
    audience: null,
    ingest_role: null,
  };
}

export function readHead(text: string): { meta: PreviewMeta; body: string } {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (lines[0]?.trim() !== "---" || end < 0) return { meta: emptyMeta(), body: text };
  const fields = new Map(
    lines
      .slice(1, end)
      .map((line) => /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/.exec(line))
      .filter((match): match is RegExpExecArray => match !== null)
      .map((match) => [match[1] ?? "", scalar(match[2] ?? "")] as const),
  );
  const field = (key: string) => fields.get(key) ?? null;
  return {
    meta: {
      doc_code: field("doc_id"),
      title: field("title"),
      tenant_id: field("tenant_id"),
      version: field("version"),
      lifecycle: oneOf(LIFECYCLES, field("status")),
      effective_from: dateOf(field("effective_from")),
      effective_to: dateOf(field("effective_to")),
      audience: oneOf(AUDIENCES, field("audience")),
      ingest_role: oneOf(ROLES, field("ingest_role")),
    },
    body: lines.slice(end + 1).join("\n"),
  };
}

// -- outline and chunks --------------------------------------------------------------------------------------

interface Section {
  level: number;
  title: string;
  body: string;
}

/** Level 0 is the text before the first heading; only headings of level 1-3 start a section. */
export function sectionsOf(body: string): Section[] {
  const lines = body.split(/\r?\n/);
  const scan = lines.reduce<{
    fenced: boolean;
    heads: { index: number; level: number; title: string }[];
  }>(
    (state, line, index) => {
      if (/^\s*(```|~~~)/.test(line)) return { ...state, fenced: !state.fenced };
      const found = state.fenced ? null : /^(#{1,3})\s+(.+?)\s*#*\s*$/.exec(line);
      if (!found) return state;
      return {
        ...state,
        heads: [...state.heads, { index, level: found[1]?.length ?? 1, title: found[2] ?? "" }],
      };
    },
    { fenced: false, heads: [] },
  );
  const first = scan.heads[0]?.index ?? lines.length;
  const preamble = { level: 0, title: "", body: lines.slice(0, first).join("\n").trim() };
  const headed = scan.heads.map((head, position) => ({
    level: head.level,
    title: head.title,
    body: lines
      .slice(head.index + 1, scan.heads[position + 1]?.index ?? lines.length)
      .join("\n")
      .trim(),
  }));
  return [preamble, ...headed];
}

/** Sections that carry text: `##`/`###` when the file has them, else whatever has text (a flat file). */
function carriers(sections: readonly Section[]): Section[] {
  const withText = sections.filter((section) => section.body !== "");
  const deep = withText.filter((section) => section.level === 2 || section.level === 3);
  return deep.length > 0 ? deep : withText;
}

const chunksFor = (chars: number): number => Math.max(1, Math.ceil(chars / CHUNK_CHARS));

/** Sections under 150 characters join the previous one (their node counts 0 chunks). */
function chunkCounts(items: readonly Section[]): Map<Section, number> {
  const groups = items.reduce<{ head: Section; chars: number }[]>((acc, section) => {
    const last = acc[acc.length - 1];
    if (last && section.body.length < MIN_CHUNK_CHARS) {
      return [...acc.slice(0, -1), { ...last, chars: last.chars + section.body.length }];
    }
    return [...acc, { head: section, chars: section.body.length }];
  }, []);
  return new Map(groups.map((group) => [group.head, chunksFor(group.chars)]));
}

function outlineFrom(
  sections: readonly Section[],
  counts: ReadonlyMap<Section, number>,
): OutlineNode[] {
  return sections
    .filter((section) => section.level > 0)
    .map((section) => ({
      level: section.level,
      title: section.title,
      chunks: counts.get(section) ?? 0,
      chars: section.body.length,
    }));
}

function tableCount(body: string): number {
  return body
    .split(/\r?\n/)
    .map((line) => line.trim().startsWith("|"))
    .reduce((count, isRow, index, rows) => (isRow && !rows[index - 1] ? count + 1 : count), 0);
}

// -- warnings ------------------------------------------------------------------------------------------------

const PHONE = /(?<!\d)(?:\+84|0)\d{9}(?!\d)|(?<!\d)0\d{2,3}[ .]\d{3}[ .]\d{3,4}(?!\d)/;
const CCCD = /(?<!\d)\d{12}(?!\d)/;
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/;

function personalData(body: string): PreviewWarning[] {
  const kinds = [
    ...(PHONE.test(body) ? ["số điện thoại"] : []),
    ...(CCCD.test(body) ? ["số CCCD"] : []),
    ...(EMAIL.test(body) ? ["email"] : []),
  ];
  if (kinds.length === 0) return [];
  return [
    {
      code: "personal_data",
      level: "warn",
      text: `Có ${kinds.join(", ")} trong văn bản. Kho không dành cho dữ liệu bệnh nhân.`,
      fix: "Kiểm tra lại; nếu là số của phòng khám thì giữ, nếu là của khách thì xóa khỏi tệp.",
    },
  ];
}

function internalScript(sections: readonly Section[], audience: Audience | null): PreviewWarning[] {
  if (audience === "staff") return [];
  const hits = sections.filter((section) => /kịch bản|nội bộ/i.test(section.title));
  if (hits.length === 0) return [];
  const names = hits
    .slice(0, 2)
    .map((section) => `"${section.title}"`)
    .join(", ");
  return [
    {
      code: "internal_script",
      level: audience === "patient" ? "warn" : "info",
      text: `Có ${hits.length} mục giống kịch bản nội bộ (${names}) mà tài liệu cho phép bệnh nhân thấy.`,
      fix: "Đặt đối tượng Nội bộ, hoặc tách các mục này thành nguồn riêng.",
    },
  ];
}

function tenantWarning(meta: PreviewMeta): PreviewWarning[] {
  if (!meta.tenant_id || meta.tenant_id === TENANT) return [];
  return [
    {
      code: "tenant",
      level: "error",
      text: `Tài liệu của phòng khám ${meta.tenant_id}, không phải phòng khám này.`,
    },
  ];
}

function challengeWarning(meta: PreviewMeta): PreviewWarning[] {
  if (meta.ingest_role !== "challenge" || store.settings.benchmark_mode) return [];
  return [
    {
      code: "challenge",
      level: "error",
      text: "Tài liệu thử thách (ingest_role: challenge) không vào kho thường.",
      fix: "Bật chế độ benchmark trong Cài đặt nếu đang chạy bộ đo.",
    },
  ];
}

function relatedSources(meta: PreviewMeta, title: string, hash: string) {
  const sameCode = meta.doc_code
    ? store.sources.find((source) => source.doc_code === meta.doc_code)
    : undefined;
  const sameTitle = sameCode
    ? undefined
    : store.sources.find((source) => fold(source.title) === fold(title));
  const remembered = hashes.get(hash);
  const sameContent =
    remembered && store.sources.some((source) => source.id === remembered.id) ? remembered : null;
  return { sameCode, sameTitle, sameContent };
}

// -- one input -----------------------------------------------------------------------------------------------

const EXTENSION_FORMAT: Record<string, SourceFormat> = {
  ".md": "md",
  ".txt": "txt",
  ".docx": "docx",
  ".xlsx": "xlsx",
  ".pdf": "pdf",
};

function formatOf(input: PreviewInput): SourceFormat {
  if (input.kind === "text") return "text";
  const dot = input.name.lastIndexOf(".");
  return EXTENSION_FORMAT[dot < 0 ? "" : input.name.slice(dot).toLowerCase()] ?? "txt";
}

function nameWithoutExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(0, dot) : name;
}

export interface Parsed {
  item: PreviewItem;
  /** The Markdown kept for the detail page (absent for files read from their name only). */
  markdown: string | null;
  hash: string;
}

function blank(input: PreviewInput, format: SourceFormat): PreviewItem {
  return {
    key: input.key,
    name: input.name,
    format,
    size: input.size,
    meta: emptyMeta(),
    outline: [],
    chunk_count: 0,
    avg_chars: 0,
    tables_split: 0,
    warnings: [],
    same_code_as: null,
    same_content_as: null,
    error: null,
  };
}

/** A file the browser sent as base64: nothing is read, the result is a plausible guess from the name. */
function fromName(input: PreviewInput, format: SourceFormat): Parsed {
  const base = blank(input, format);
  const isScan = format === "pdf" && /scan/i.test(input.name);
  if (isScan)
    return {
      item: { ...base, error: "PDF là ảnh scan, chưa đọc được chữ" },
      markdown: null,
      hash: "",
    };
  const title = nameWithoutExtension(input.name);
  const outline: OutlineNode[] = [
    { level: 1, title, chunks: 0, chars: 120 },
    { level: 2, title: "Giới thiệu", chunks: 5, chars: 4_100 },
    { level: 2, title: "Chi tiết", chunks: 7, chars: 5_600 },
  ];
  const warnings: PreviewWarning[] =
    format === "pdf"
      ? [
          {
            code: "no_headings",
            level: "warn",
            text: "Không tìm thấy tiêu đề nào (PDF mất định dạng?).",
            fix: "Dựng lại bằng AI hoặc chỉnh tay ở trang chi tiết nguồn.",
          },
        ]
      : [];
  const hash = hashOf(`${input.name}:${input.size}`);
  const related = relatedSources(emptyMeta(), title, hash);
  return {
    item: {
      ...base,
      outline: format === "pdf" ? [] : outline,
      chunk_count: 12,
      avg_chars: 810,
      tables_split: format === "xlsx" ? 1 : 0,
      warnings,
      same_content_as: related.sameContent,
    },
    markdown: null,
    hash,
  };
}

function fromText(input: PreviewInput, text: string, format: SourceFormat): Parsed {
  const { meta, body } = readHead(text);
  const sections = sectionsOf(body);
  const counts = chunkCounts(carriers(sections));
  const chunkTotal = [...counts.values()].reduce((sum, count) => sum + count, 0);
  const charTotal = carriers(sections).reduce((sum, section) => sum + section.body.length, 0);
  const title = meta.title ?? nameWithoutExtension(input.name);
  const hash = hashOf(body);
  const related = relatedSources(meta, title, hash);
  const noHeadings = sections.every((section) => section.level === 0);
  const warnings: PreviewWarning[] = [
    ...tenantWarning(meta),
    ...challengeWarning(meta),
    ...(noHeadings
      ? [
          {
            code: "no_headings",
            level: "warn" as const,
            text: "Không tìm thấy tiêu đề nào: tài liệu sẽ bị cắt theo độ dài.",
            fix: "Thêm tiêu đề (# ##) vào văn bản cho máy chia đoạn đúng.",
          },
        ]
      : []),
    ...personalData(body),
    ...internalScript(sections, meta.audience),
    ...(related.sameTitle
      ? [
          {
            code: "same_title",
            level: "info" as const,
            text: `Trùng tên với nguồn "${related.sameTitle.title}".`,
            fix: 'Chọn "Thay thế nguồn cũ" ở bước Thông tin nếu đây là bản mới.',
          },
        ]
      : []),
  ];
  const item: PreviewItem = {
    ...blank(input, format),
    meta,
    outline: outlineFrom(sections, counts),
    chunk_count: chunkTotal,
    avg_chars: chunkTotal === 0 ? 0 : Math.round(charTotal / chunkTotal),
    tables_split: tableCount(body),
    warnings,
    same_code_as: related.sameCode
      ? {
          id: related.sameCode.id,
          title: related.sameCode.title,
          version: related.sameCode.version,
        }
      : null,
    same_content_as: related.sameContent,
  };
  return { item, markdown: body.trim(), hash };
}

export function parseInput(input: PreviewInput): Parsed {
  const format = formatOf(input);
  if (input.text !== undefined) return fromText(input, input.text, format);
  return fromName(input, format);
}
