// A tiny Markdown reader for the staff guide. An article is the text of a knowledge-base source, written by the
// clinic in `/admin/kb`; the page must show it as headings, paragraphs and lists WITHOUT ever turning text into
// HTML (no dangerouslySetInnerHTML): this module returns plain data and React renders it, so a `<script>` typed
// into an article is shown as text. Supported: `##`/`###` headings, paragraphs, `-`/`*` and `1.` lists, `>`
// quotes, `**bold**`, `*italic*`, `` `code` `` and `[text](url)` links whose url is http(s) or a path of this
// app. Anything else is plain text.

export type Inline =
  | { kind: "text"; text: string }
  | { kind: "bold"; text: string }
  | { kind: "italic"; text: string }
  | { kind: "code"; text: string }
  | { kind: "link"; text: string; href: string };

export type Block =
  | { kind: "heading"; level: 2 | 3; text: string }
  | { kind: "paragraph"; inline: Inline[] }
  | { kind: "list"; ordered: boolean; items: Inline[][] }
  | { kind: "quote"; inline: Inline[] };

const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const BULLET = /^\s*[-*+]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const QUOTE = /^\s*>\s?(.*)$/;
const INLINE =
  /(\*\*(?<bold>[^*]+)\*\*)|(\*(?<italic>[^*\s][^*]*)\*)|(`(?<code>[^`]+)`)|(\[(?<label>[^\]]+)\]\((?<href>[^)\s]+)\))/g;

/** http(s) and paths of this app only: never `javascript:`, `data:` or protocol-relative urls. */
export function safeHref(href: string): string | null {
  if (/^https?:\/\//i.test(href)) return href;
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  return null;
}

function inlineOf(groups: Record<string, string | undefined>): Inline {
  const { bold, italic, code, label = "", href = "" } = groups;
  if (bold !== undefined) return { kind: "bold", text: bold };
  if (italic !== undefined) return { kind: "italic", text: italic };
  if (code !== undefined) return { kind: "code", text: code };
  const safe = safeHref(href);
  return safe === null ? { kind: "text", text: label } : { kind: "link", text: label, href: safe };
}

export function parseInline(source: string): Inline[] {
  const matches = [...source.matchAll(INLINE)];
  const parts = matches.flatMap((match, i): Inline[] => {
    const previousEnd =
      i === 0 ? 0 : (matches[i - 1]?.index ?? 0) + (matches[i - 1]?.[0].length ?? 0);
    const gap = source.slice(previousEnd, match.index);
    const token = inlineOf(match.groups ?? {});
    return gap === "" ? [token] : [{ kind: "text", text: gap }, token];
  });
  const lastMatch = matches.at(-1);
  const tailStart = lastMatch === undefined ? 0 : lastMatch.index + lastMatch[0].length;
  const tail = source.slice(tailStart);
  return tail === "" ? parts : [...parts, { kind: "text", text: tail }];
}

type Open =
  | { kind: "none" }
  | { kind: "paragraph"; lines: readonly string[] }
  | { kind: "list"; ordered: boolean; items: readonly string[] };

type State = { blocks: readonly Block[]; open: Open };

const EMPTY: State = { blocks: [], open: { kind: "none" } };

function closeOpen(state: State): State {
  const { open } = state;
  if (open.kind === "paragraph") {
    const block: Block = { kind: "paragraph", inline: parseInline(open.lines.join(" ")) };
    return { blocks: [...state.blocks, block], open: { kind: "none" } };
  }
  if (open.kind === "list") {
    const block: Block = {
      kind: "list",
      ordered: open.ordered,
      items: open.items.map((item) => parseInline(item)),
    };
    return { blocks: [...state.blocks, block], open: { kind: "none" } };
  }
  return state;
}

function withBlock(state: State, block: Block): State {
  const closed = closeOpen(state);
  return { blocks: [...closed.blocks, block], open: { kind: "none" } };
}

function addListItem(state: State, ordered: boolean, text: string): State {
  const { open } = state;
  if (open.kind === "list" && open.ordered === ordered) {
    return { ...state, open: { ...open, items: [...open.items, text] } };
  }
  const closed = closeOpen(state);
  return { ...closed, open: { kind: "list", ordered, items: [text] } };
}

function addLine(state: State, raw: string): State {
  const line = raw.trimEnd();
  if (line.trim() === "") return closeOpen(state);

  const heading = HEADING.exec(line);
  if (heading) {
    const level = (heading[1] ?? "##").length <= 2 ? 2 : 3;
    return withBlock(state, { kind: "heading", level, text: heading[2] ?? "" });
  }
  const bullet = BULLET.exec(line);
  if (bullet) return addListItem(state, false, bullet[1] ?? "");
  const numbered = NUMBERED.exec(line);
  if (numbered) return addListItem(state, true, numbered[1] ?? "");
  const quote = QUOTE.exec(line);
  if (quote) return withBlock(state, { kind: "quote", inline: parseInline(quote[1] ?? "") });

  const { open } = state;
  if (open.kind === "list" && /^\s+\S/.test(raw)) {
    // A wrapped line of a list item.
    const items = open.items.with(-1, `${open.items.at(-1) ?? ""} ${line.trim()}`);
    return { ...state, open: { ...open, items } };
  }
  if (open.kind === "paragraph") {
    return { ...state, open: { kind: "paragraph", lines: [...open.lines, line.trim()] } };
  }
  const closed = closeOpen(state);
  return { ...closed, open: { kind: "paragraph", lines: [line.trim()] } };
}

/** Blocks of an article. A heading deeper than `###` is shown as `###`; an `#` title is shown as `##` (the page
 * already has the title as its own `h2`). */
export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  return [...closeOpen(lines.reduce(addLine, EMPTY)).blocks];
}
