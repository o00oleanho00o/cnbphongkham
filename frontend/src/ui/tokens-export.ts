// Turns `tokens.css` into the JSON the KMP app consumes. Pure functions: `scripts/export-tokens.ts` does the
// file I/O and `tokens.test.ts` checks that the committed tokens.json equals what this produces.

export type TokenGroup =
  "color" | "radius" | "shadow" | "text" | "space" | "layout" | "breakpoint" | "z" | "font";

export type TokenMap = Record<string, string>;

export type TokensJson = {
  $schema: string;
  version: 1;
  source: string;
  /** `light` is the `@theme` block, `dark` only the colours that change in dark mode. */
  color: { light: TokenMap; dark: TokenMap };
  radius: TokenMap;
  shadow: TokenMap;
  text: TokenMap;
  space: TokenMap;
  layout: TokenMap;
  breakpoint: TokenMap;
  z: TokenMap;
  font: TokenMap;
};

type Declaration = { name: string; value: string };

const GROUP_PREFIXES: readonly (readonly [string, TokenGroup])[] = [
  ["--color-", "color"],
  ["--radius-", "radius"],
  ["--shadow-", "shadow"],
  ["--text-", "text"],
  ["--space-", "space"],
  ["--layout-", "layout"],
  ["--breakpoint-", "breakpoint"],
  ["--z-", "z"],
  ["--font-", "font"],
];

const THEME_BLOCK = /@theme(?:\s+static)?\s*\{/;
const DARK_BLOCK = /\.dark\s*\{/;

function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, "");
}

/** Index just after the brace that closes the block whose opening brace is at `openIndex`. */
function closingIndex(css: string, openIndex: number): number {
  const depthAt = [...css.slice(openIndex)].reduce<{ depth: number; end: number }>(
    (state, char, offset) => {
      if (state.end >= 0) return state;
      const depth = state.depth + (char === "{" ? 1 : 0) - (char === "}" ? 1 : 0);
      return { depth, end: depth === 0 ? openIndex + offset : -1 };
    },
    { depth: 0, end: -1 },
  );
  if (depthAt.end < 0) throw new Error("unbalanced braces in tokens.css");
  return depthAt.end;
}

function blockBody(css: string, header: RegExp): string {
  const match = header.exec(css);
  if (!match) throw new Error(`block not found: ${header}`);
  const open = match.index + match[0].length - 1;
  return css.slice(open + 1, closingIndex(css, open));
}

function declarations(body: string): Declaration[] {
  return [...body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/g)].map((m) => ({
    name: m[1] ?? "",
    value: (m[2] ?? "").trim().replace(/\s+/g, " "),
  }));
}

function groupOf(name: string): { group: TokenGroup; key: string } {
  const hit = GROUP_PREFIXES.find(([prefix]) => name.startsWith(prefix));
  if (!hit) throw new Error(`token ${name} has no known group prefix`);
  return { group: hit[1], key: name.slice(hit[0].length) };
}

function toMap(items: Declaration[], group: TokenGroup): TokenMap {
  return Object.fromEntries(
    items
      .map((d) => ({ ...groupOf(d.name), value: d.value }))
      .filter((d) => d.group === group)
      .map((d) => [d.key, d.value]),
  );
}

export function parseTokens(css: string): TokensJson {
  const clean = stripComments(css);
  const light = declarations(blockBody(clean, THEME_BLOCK));
  const dark = declarations(blockBody(clean, DARK_BLOCK));
  const nonColorOverride = dark.find((d) => groupOf(d.name).group !== "color");
  if (nonColorOverride)
    throw new Error(`.dark may only override colours: ${nonColorOverride.name}`);
  return {
    $schema: "./tokens.schema.json",
    version: 1,
    source: "src/ui/tokens.css",
    color: { light: toMap(light, "color"), dark: toMap(dark, "color") },
    radius: toMap(light, "radius"),
    shadow: toMap(light, "shadow"),
    text: toMap(light, "text"),
    space: toMap(light, "space"),
    layout: toMap(light, "layout"),
    breakpoint: toMap(light, "breakpoint"),
    z: toMap(light, "z"),
    font: toMap(light, "font"),
  };
}

export function renderTokensJson(css: string): string {
  return `${JSON.stringify(parseTokens(css), null, 2)}\n`;
}
