/** A skill as a Markdown file: `---` name, description (and kind, scopes, status when they are not the usual) `---`,
 * then the text. Reads a file a person adds, and writes one for download. */
import { KINDS, MAX_DESCRIPTION, STATUSES } from "./logic";
import type { Item, Kind, Status } from "./types";

export interface SkillFile {
  fileName: string;
  kind: Kind;
  name: string;
  description: string;
  body: string;
  scopes: string[];
  status: Status;
}

const LINE = /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/;
const LIST_ITEM = /^\s*-\s+(.+)$/;

function unquote(raw: string): string {
  const value = raw.trim();
  const quoted = /^(["'])(.*)\1$/.exec(value);
  return quoted ? (quoted[2] ?? "") : value;
}

/** `a, b`, `[a, b]` or the lines `- a` that follow the key. */
function listOf(raw: string, following: readonly string[]): string[] {
  const inline = raw
    .trim()
    .replace(/^\[|\]$/g, "")
    .split(",")
    .map((part) => unquote(part))
    .filter((part) => part !== "");
  const lines = following.map((line) => LIST_ITEM.exec(line)?.[1]).filter((value): value is string => !!value);
  return [...inline, ...lines.map(unquote)];
}

function oneOf<T extends string>(allowed: readonly { id: T }[], value: string | undefined, fallback: T): T {
  return allowed.find((option) => option.id === value?.trim())?.id ?? fallback;
}

export function slug(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Mn}/gu, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

interface Head {
  fields: Map<string, string>;
  lists: Map<string, string[]>;
  body: string;
}

/** The `---` block at the top and what follows it; a file without one is all body. */
function readHead(text: string): Head {
  const lines = text.replace(/^﻿/, "").replace(/\r\n/g, "\n").split("\n");
  const empty: Head = { fields: new Map(), lists: new Map(), body: lines.join("\n").trim() };
  if (lines[0]?.trim() !== "---") return empty;
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (end < 0) return empty;
  const head = lines.slice(1, end);
  const entries = head.map((line, index) => ({ match: LINE.exec(line), index })).filter((entry) => entry.match);
  const fields = new Map(entries.map(({ match }) => [match?.[1] ?? "", unquote(match?.[2] ?? "")]));
  const lists = new Map(
    entries.map(({ match, index }) => [match?.[1] ?? "", listOf(match?.[2] ?? "", followingLines(head, index))]),
  );
  return { fields, lists, body: lines.slice(end + 1).join("\n").trim() };
}

/** The lines after the `key:` line at `index`, up to the next `key:` line: the `- a` items of a list. */
function followingLines(head: readonly string[], index: number): string[] {
  const rest = head.slice(index + 1);
  const next = rest.findIndex((line) => LINE.test(line));
  return next < 0 ? rest : rest.slice(0, next);
}

function firstLine(text: string): string {
  const line = text.split("\n").find((candidate) => candidate.trim() !== "") ?? "";
  return line.replace(/^#+\s*/, "").trim().slice(0, MAX_DESCRIPTION);
}

export function parseSkillFile(fileName: string, text: string): SkillFile {
  const { fields, lists, body } = readHead(text);
  const base = fileName.replace(/\.[^.]+$/, "");
  return {
    fileName,
    kind: oneOf(KINDS, fields.get("kind"), "skill"),
    name: fields.get("name") || slug(base),
    description: fields.get("description") || firstLine(body),
    body,
    scopes: lists.get("scopes") ?? [],
    status: oneOf(STATUSES, fields.get("status"), "active"),
  };
}

/** The item as the file a person can keep or send on; the same shape `parseSkillFile` reads. */
export function toSkillFile(item: Pick<Item, "kind" | "name" | "description" | "body" | "scopes" | "status">): string {
  const head = [
    `name: ${item.name}`,
    `description: ${item.description}`,
    ...(item.kind === "skill" ? [] : [`kind: ${item.kind}`]),
    ...(item.scopes.length === 0 ? [] : [`scopes: ${item.scopes.join(", ")}`]),
    ...(item.status === "active" ? [] : [`status: ${item.status}`]),
  ];
  return `---\n${head.join("\n")}\n---\n\n${item.body.trim()}\n`;
}

export function downloadText(fileName: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  URL.revokeObjectURL(url);
}
