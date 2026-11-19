/** Pure rules of the services tab: codes, aliases, the form, reading a pasted table and planning an import. */
import type { Service, ServiceBody } from "../types";

export const CODE_PATTERN = /^[A-Z0-9_]+$/;
export const CODE_RULE = "Mã gồm chữ in hoa không dấu, chữ số và dấu gạch dưới (ví dụ HORI_LASER).";
const CODE_MAX = 40;

export const INTRO_TEXT =
  'Tên gọi khác giúp tìm đúng khi khách gọi khác (ví dụ "hori" = "bớt Hori"); có hiệu lực ngay cho tìm kiếm.';

export function normaliseCode(raw: string): string {
  return raw.trim().toUpperCase();
}

/** Lower case without accents, for searching and for matching table headers. */
export function foldText(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase();
}

/** `a, b; c` as a list of trimmed, non-empty words. */
export function splitList(text: string): string[] {
  return text
    .split(/[;,]/)
    .map((word) => word.trim())
    .filter((word) => word !== "");
}

/** Adds the words of `raw` to the list; one already there (any letter case) is not added twice. */
export function addWords(words: readonly string[], raw: string): string[] {
  return splitList(raw).reduce<string[]>(
    (all, word) => (all.some((have) => have.toLowerCase() === word.toLowerCase()) ? all : [...all, word]),
    [...words],
  );
}

export function removeWord(words: readonly string[], word: string): string[] {
  return words.filter((have) => have !== word);
}

export function matchesQuery(service: Service, query: string): boolean {
  const needle = foldText(query.trim());
  if (needle === "") return true;
  const haystack = [service.code, service.name, service.description, ...service.aliases, ...service.branches];
  return haystack.some((text) => foldText(text).includes(needle));
}

export function codeProblem(code: string, services: readonly Service[], ownId: string | null): string | null {
  if (code === "") return "Nhập mã dịch vụ.";
  if (code.length > CODE_MAX) return `Mã dài tối đa ${CODE_MAX} ký tự.`;
  if (!CODE_PATTERN.test(code)) return CODE_RULE;
  const taken = services.some((service) => service.id !== ownId && service.code === code);
  return taken ? "Mã này đã có, mỗi dịch vụ một mã." : null;
}

// -- the add / edit form -----------------------------------------------------------------------------------

export interface ServiceForm {
  code: string;
  name: string;
  description: string;
  aliases: string[];
  branches: string[];
  enabled: boolean;
}

export const EMPTY_FORM: ServiceForm = {
  code: "",
  name: "",
  description: "",
  aliases: [],
  branches: [],
  enabled: true,
};

export function formOf(service: Service | null): ServiceForm {
  if (!service) return EMPTY_FORM;
  const { code, name, description, aliases, branches, enabled } = service;
  return { code, name, description, aliases, branches, enabled };
}

export interface FormProblems {
  code: string | null;
  name: string | null;
}

export function formProblems(form: ServiceForm, services: readonly Service[], ownId: string | null): FormProblems {
  return {
    code: codeProblem(normaliseCode(form.code), services, ownId),
    name: form.name.trim() === "" ? "Nhập tên dịch vụ." : null,
  };
}

export function hasProblem(problems: FormProblems): boolean {
  return problems.code !== null || problems.name !== null;
}

export function bodyOf(form: ServiceForm): ServiceBody {
  return {
    code: normaliseCode(form.code),
    name: form.name.trim(),
    aliases: form.aliases,
    description: form.description.trim(),
    branches: form.branches,
    enabled: form.enabled,
  };
}

export function deleteWarning(service: Service): string {
  if (service.chunk_count === 0) return "Chưa có đoạn nào gắn nhãn dịch vụ này. Không hoàn tác được.";
  return `${service.chunk_count} đoạn đang gắn nhãn ${service.code} sẽ mất nhãn này, nên tìm theo dịch vụ sẽ không còn thấy chúng. Không hoàn tác được.`;
}

export function codeChangeWarning(service: Service, newCode: string): string {
  const labelled =
    service.chunk_count === 0
      ? "Chưa có đoạn nào gắn nhãn này"
      : `${service.chunk_count} đoạn đang gắn nhãn ${service.code}`;
  return `${labelled}. Nhãn phụ thuộc vào mã: đổi ${service.code} thành ${newCode} sẽ đổi nhãn theo, còn quy tắc hay công cụ nào gọi mã cũ sẽ không tìm thấy dịch vụ này nữa.`;
}

// -- reading a pasted table (CSV or Markdown) ---------------------------------------------------------------

type Column = "code" | "name" | "aliases" | "description" | "branches";

const COLUMN_ORDER: readonly Column[] = ["code", "name", "aliases", "description", "branches"];

const HEADER_WORDS: Record<Column, readonly string[]> = {
  code: ["code", "ma", "ma dich vu"],
  name: ["name", "ten", "ten dich vu"],
  aliases: ["aliases", "alias", "ten goi khac"],
  description: ["description", "mo ta"],
  branches: ["branches", "chi nhanh"],
};

export interface TableProblem {
  /** 1-based line of the pasted text. */
  line: number;
  text: string;
  reason: string;
}

export interface TableRead {
  rows: ServiceBody[];
  problems: TableProblem[];
}

interface CsvState {
  cells: string[];
  current: string;
  quoted: boolean;
}

function csvStep(state: CsvState, char: string, delimiter: string): CsvState {
  if (char === '"') return { ...state, quoted: !state.quoted };
  if (char === delimiter && !state.quoted) return { cells: [...state.cells, state.current], current: "", quoted: false };
  return { ...state, current: state.current + char };
}

function splitCsv(line: string, delimiter: string): string[] {
  const end = [...line].reduce<CsvState>((state, char) => csvStep(state, char, delimiter), {
    cells: [],
    current: "",
    quoted: false,
  });
  return [...end.cells, end.current].map((cell) => cell.trim());
}

function splitMarkdown(line: string): string[] {
  const inner = line.replace(/^\|/, "").replace(/\|$/, "");
  return inner.split("|").map((cell) => cell.trim());
}

const isSeparator = (line: string): boolean => /^[\s|:-]+$/.test(line) && line.includes("-");

/** Comma unless the first line only splits on a tab or a semicolon. */
function pickDelimiter(firstLine: string): string {
  return ["\t", ",", ";"].find((delimiter) => firstLine.includes(delimiter)) ?? ",";
}

interface TableRow {
  line: number;
  text: string;
  cells: string[];
}

function readRows(text: string): TableRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((raw, index) => ({ line: index + 1, text: raw.trim() }))
    .filter((entry) => entry.text !== "" && !isSeparator(entry.text));
  const first = lines.find((entry) => !entry.text.startsWith("|"));
  const delimiter = pickDelimiter(first?.text ?? "");
  return lines.map((entry) => ({
    ...entry,
    cells: entry.text.startsWith("|") ? splitMarkdown(entry.text) : splitCsv(entry.text, delimiter),
  }));
}

function columnOf(cell: string): Column | null {
  const folded = foldText(cell.trim());
  return COLUMN_ORDER.find((column) => HEADER_WORDS[column].includes(folded)) ?? null;
}

/** The columns of a header row (code and name must both be named), or null when the row is data. */
function headerColumns(cells: readonly string[]): (Column | null)[] | null {
  const columns = cells.map(columnOf);
  const named = new Set(columns);
  return named.has("code") && named.has("name") ? columns : null;
}

function cellOf(row: TableRow, columns: readonly (Column | null)[], column: Column): string {
  const index = columns.indexOf(column);
  return index < 0 ? "" : (row.cells[index] ?? "");
}

function rowProblem(code: string, name: string, seen: ReadonlySet<string>): string | null {
  if (code === "") return "Thiếu mã dịch vụ.";
  if (!CODE_PATTERN.test(code)) return `Mã "${code}" không hợp lệ. ${CODE_RULE}`;
  if (name === "") return "Thiếu tên dịch vụ.";
  return seen.has(code) ? `Mã ${code} đã có ở dòng trên.` : null;
}

interface ReadState extends TableRead {
  seen: ReadonlySet<string>;
}

function readStep(state: ReadState, row: TableRow, columns: readonly (Column | null)[]): ReadState {
  const code = normaliseCode(cellOf(row, columns, "code"));
  const name = cellOf(row, columns, "name").trim();
  const reason = rowProblem(code, name, state.seen);
  if (reason) return { ...state, problems: [...state.problems, { line: row.line, text: row.text, reason }] };
  const body: ServiceBody = {
    code,
    name,
    aliases: addWords([], cellOf(row, columns, "aliases")),
    description: cellOf(row, columns, "description").trim(),
    branches: addWords([], cellOf(row, columns, "branches")),
    enabled: true,
  };
  return { ...state, rows: [...state.rows, body], seen: new Set([...state.seen, code]) };
}

/**
 * Reads pasted text: a Markdown table or CSV (comma, tab or semicolon), with or without a header line. The columns
 * are code, name, aliases (separated by `;` or `,`), description, branches. Rows that cannot be read are listed.
 */
export function parseServiceTable(text: string): TableRead {
  const rows = readRows(text);
  const header = rows[0] ? headerColumns(rows[0].cells) : null;
  const columns = header ?? COLUMN_ORDER;
  const data = header ? rows.slice(1) : rows;
  const { rows: parsed, problems } = data.reduce<ReadState>((state, row) => readStep(state, row, columns), {
    rows: [],
    problems: [],
    seen: new Set(),
  });
  return { rows: parsed, problems };
}

// -- planning an import ------------------------------------------------------------------------------------

export interface ImportRow {
  service: Service;
  /** The service of the same code already in the catalogue: the row updates it. */
  existing: Service | null;
}

export function importRows(preview: readonly Service[], existing: readonly Service[]): ImportRow[] {
  const byCode = new Map(existing.map((service) => [service.code, service]));
  return preview.map((service) => ({ service, existing: byCode.get(normaliseCode(service.code)) ?? null }));
}

const mergeWords = (base: readonly string[], extra: readonly string[]): string[] =>
  extra.reduce<string[]>((all, word) => addWords(all, word), [...base]);

/** An update keeps what the catalogue has: aliases and branches are added to, an empty description is not applied. */
export function updateBody(row: Service, existing: Service): ServiceBody {
  return {
    code: existing.code,
    name: row.name.trim() || existing.name,
    aliases: mergeWords(existing.aliases, row.aliases),
    description: row.description.trim() || existing.description,
    branches: mergeWords(existing.branches, row.branches),
    enabled: existing.enabled,
  };
}

export function createBody(row: Service): ServiceBody {
  return {
    code: normaliseCode(row.code),
    name: row.name.trim(),
    aliases: row.aliases,
    description: row.description.trim(),
    branches: row.branches,
    enabled: true,
  };
}

export function importSummary(done: number, failed: number): string {
  if (failed === 0) return `Đã nhập ${done} dịch vụ.`;
  return `Đã nhập ${done} dịch vụ, ${failed} dịch vụ lỗi.`;
}
