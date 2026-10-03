import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { validateJsonSchema, type Schema } from "./json-schema-lite";
import { parseTokens, renderTokensJson, type TokensJson } from "./tokens-export";

const read = (name: string): string =>
  readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

const css = read("./tokens.css");
const committed: TokensJson = JSON.parse(read("./tokens.json"));
const schema: Schema = JSON.parse(read("./tokens.schema.json"));

/** Names the existing screens already use (globals.css before U0): they must keep resolving. */
const LEGACY_COLORS = [
  "brand-50",
  "brand-100",
  "brand-200",
  "brand-400",
  "brand-500",
  "brand-600",
  "brand-700",
  "canvas",
  "surface",
  "ink",
  "ink-soft",
  "line",
  "tile",
];

function channel(hex: string, start: number): number {
  const value = parseInt(hex.slice(start, start + 2), 16) / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  return 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
}

/** WCAG contrast ratio of two #rrggbb colours. */
function contrast(foreground: string, background: string): number {
  const [light, dark] = [luminance(foreground), luminance(background)].toSorted((a, b) => b - a);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

const colorOf = (mode: "light" | "dark", name: string): string => {
  const value = mode === "dark" ? committed.color.dark[name] : undefined;
  return value ?? committed.color.light[name] ?? "";
};

describe("tokens.json", () => {
  it("is exactly what tokens.css exports (run `pnpm tokens` after editing the CSS)", () => {
    expect(JSON.stringify(committed, null, 2) + "\n").toBe(renderTokensJson(css));
  });

  it("validates against tokens.schema.json", () => {
    expect(validateJsonSchema(schema, committed)).toEqual([]);
  });

  it("rejects a value that is not a colour", () => {
    const broken = structuredClone(committed);
    broken.color.light["ink"] = "navy";
    expect(validateJsonSchema(schema, broken)).not.toEqual([]);
  });

  it("keeps the colour names the existing screens use", () => {
    LEGACY_COLORS.forEach((name) => expect(committed.color.light[name]).toMatch(/^#[0-9a-f]{6}$/));
  });

  it("only overrides in dark mode what exists in light mode", () => {
    const missing = Object.keys(committed.color.dark).filter(
      (name) => !(name in committed.color.light),
    );
    expect(missing).toEqual([]);
  });

  it("carries the identity values of the old Pema web", () => {
    expect(committed.color.light["brand-500"]).toBe("#0b4f94");
    expect(committed.color.light["brand-600"]).toBe("#083a6e");
    expect(committed.color.light["canvas"]).toBe("#f4f8fb");
    expect(committed.radius["card"]).toBe("14px");
    expect(committed.layout["sidebar-w"]).toBe("232px");
    expect(committed.breakpoint["wide"]).toBe("100rem");
  });
});

describe("parseTokens", () => {
  it("reads light values from @theme and dark overrides from .dark, ignoring comments", () => {
    const parsed = parseTokens(`
      /* --color-ghost: #000000; */
      @theme static { --color-ink: #111111; --radius-card: 14px; }
      .dark { --color-ink: #eeeeee; }`);
    expect(parsed.color.light).toEqual({ ink: "#111111" });
    expect(parsed.color.dark).toEqual({ ink: "#eeeeee" });
    expect(parsed.radius).toEqual({ card: "14px" });
  });

  it("refuses a dark override that is not a colour", () => {
    expect(() =>
      parseTokens("@theme { --color-a: #000000; } .dark { --radius-card: 1px; }"),
    ).toThrow(/only override colours/);
  });

  it("refuses a token with an unknown prefix", () => {
    expect(() => parseTokens("@theme { --mystery: 1; } .dark { }")).toThrow(/no known group/);
  });
});

describe("contrast (WCAG AA 4.5:1 for normal text)", () => {
  const modes = ["light", "dark"] as const;
  const pairs: [string, string, string][] = [
    ["ink", "surface", "body text on a card"],
    ["ink", "canvas", "body text on the page"],
    ["ink-soft", "surface", "metadata on a card"],
    ["ink-soft", "canvas", "metadata on the page"],
    ["ink-soft", "tile", "metadata on a tile"],
    ["heading", "surface", "page title"],
    ["brand-700", "brand-50", "active menu item"],
    ["link", "surface", "link and selected tab text"],
    ["success", "success-soft", "success badge"],
    ["info", "info-soft", "info badge"],
    ["warning", "warning-soft", "warning badge"],
    ["danger", "danger-soft", "danger badge"],
    ["danger", "surface", "error text on a card"],
  ];

  modes.forEach((mode) =>
    pairs.forEach(([foreground, background, what]) =>
      it(`${what} (${foreground} on ${background}) in ${mode} mode`, () => {
        expect(
          contrast(colorOf(mode, foreground), colorOf(mode, background)),
        ).toBeGreaterThanOrEqual(4.5);
      }),
    ),
  );

  it("nav badge: white text on accent-strong in light mode", () => {
    expect(contrast("#ffffff", colorOf("light", "accent-strong"))).toBeGreaterThanOrEqual(4.5);
  });
});

describe("kit sources", () => {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  const sources = readdirSync(dir)
    .filter((name) => /\.tsx?$/.test(name) && !name.includes(".test."))
    .filter((name) => name !== "kit-examples.tsx");

  it.each(sources)("%s_has_no_hard_coded_colours", (name) => {
    const text = readFileSync(`${dir}${name}`, "utf8");

    expect(text.match(/#[0-9a-fA-F]{3,8}\b|\b(?:bg|text|border)-(?:white|black)\b/g)).toBeNull();
  });
});
