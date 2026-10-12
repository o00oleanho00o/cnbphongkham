/** Reads the YAML head of a Markdown file (`---` ... `---`), the few `key: value` lines the store knows about. */
import type { Audience, Lifecycle, PreviewMeta } from "../types";

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

const LIFECYCLES: readonly Lifecycle[] = ["active", "draft", "superseded", "adversarial"];
const AUDIENCES: readonly Audience[] = ["patient", "staff"];
const ROLES = ["kb", "challenge"] as const;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const LINE = /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/;

/** `"text"`, `'text'` and bare words; `null`, `~` and nothing give null. A trailing ` # comment` is dropped. */
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
  return value !== null && DATE.test(value) ? value : null;
}

function metaFrom(fields: ReadonlyMap<string, string | null>): PreviewMeta {
  return {
    doc_code: fields.get("doc_id") ?? null,
    title: fields.get("title") ?? null,
    tenant_id: fields.get("tenant_id") ?? null,
    version: fields.get("version") ?? null,
    lifecycle: oneOf(LIFECYCLES, fields.get("status") ?? null),
    effective_from: dateOf(fields.get("effective_from") ?? null),
    effective_to: dateOf(fields.get("effective_to") ?? null),
    audience: oneOf(AUDIENCES, fields.get("audience") ?? null),
    ingest_role: oneOf(ROLES, fields.get("ingest_role") ?? null),
  };
}

export interface Frontmatter {
  meta: PreviewMeta;
  /** The text after the head (the whole text when there is no head). */
  body: string;
}

/** A head that is missing, never closed or has no readable lines gives empty meta; nothing here throws. */
export function readFrontmatter(text: string): Frontmatter {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/);
  if (lines[0]?.trim() !== "---") return { meta: emptyMeta(), body: text };
  const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (end < 0) return { meta: emptyMeta(), body: text };
  const fields = new Map(
    lines
      .slice(1, end)
      .map((line) => LINE.exec(line))
      .filter((match): match is RegExpExecArray => match !== null)
      .map((match) => [match[1] ?? "", scalar(match[2] ?? "")] as const),
  );
  return { meta: metaFrom(fields), body: lines.slice(end + 1).join("\n") };
}
