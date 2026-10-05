# U12 — Housekeeping: stale wording, tooling bugs, old-web screenshots, baseline fix

## Goal
Clear the small leftover items from the U8/W2 reports that are not product decisions, so later checkouts and later
packages do not trip on them.

## Read first
1. `HANDOFF.md` "Known gaps"/"Open items" (W2 and U8 sections) and the 2026-10-05 history-rewrite note.
2. `design-specs/README.md`, `.claude/skills/pema-web-design/SKILL.md`, `.claude/skills/pema-web-design/scripts/*.cjs`
   (`catalog-nextjs.cjs`, `pending-web.cjs`, `pending.cjs`, `web-specs.cjs`/`design-specs.cjs` → `imageLines()`),
   `design-specs/web/snapshot.json` (`meta.inventory_sha`), `design-system/colors.md` (contrast table),
   `pema-agent/frontend/src/ui/tokens.css` (`--color-brand-500`, `--color-accent-strong`, dark mode block).

## Ingredients and fixes
1. **Wording:** `design-specs/README.md` still calls `design-specs/INDEX.md` the "82-screen list" — it is the hub
   (app 82, web 384, Design System); fix the sentence. `.claude/skills/pema-web-design/SKILL.md` body still says
   "211 screens" in at least one place — the web inventory is now 384 (211 old web + 173 Next.js-only); fix every
   occurrence, keep "211" only where a sentence is specifically about the old web alone.
2. **MCP:** `get_web_screen` throws for a Next.js-only id that has no snapshot entry yet — make it return the spec
   file's content directly when a snapshot is missing (specs do not need a snapshot for ids whose behaviour notes
   were written by hand), with a clear message only when the id does not exist at all.
3. **`catalog-nextjs.cjs`:** still marks `/cashier` and `/finance` as "(sắp có)" (coming soon) — both exist since U5
   and U6; update the catalog text to reflect that, re-run whatever check regenerates/validates this file.
4. **`snapshot.json` `meta.inventory_sha`:** was hand-edited after a catalog change instead of being produced by a
   real walk of the old web. Re-run the actual snapshot step (`web-snapshot.cjs`) scoped to just recomputing the
   hash if the full walk is too slow to redo, and say in the report which you did; the field must end up correct
   for the content, not asserted by hand again.
5. **`pending-web.cjs` / `pending.cjs` baseline:** both fail because their sync baseline commit `c40ba22` is not in
   `feat/ui-parity`'s history any more (it was rewritten 2026-10-05, same tree, new hash `0c454cc` — confirm with
   `git cat-file -e 0c454cc` and that its tree matches what `c40ba22` used to point to, described in `HANDOFF.md`).
   Update the hardcoded baseline reference in both scripts (or their config) to `0c454cc`.
6. **Old-web screenshots:** `pema-agent/frontend/visual-ref/old/` is empty on a fresh checkout (git-ignored, correct
   by design) — but `PARITY-AI01-U.md` needs real old-vs-new images. Start the old web
   (`python -m http.server 4173 --bind 127.0.0.1 --directory prototype`) and run
   `.claude/skills/pema-web-design/scripts/web-shots.cjs` (or `prototype/review-desktop.cjs` with
   `PEMA_EVIDENCE_DIR` under `pema-agent/`) to regenerate the 1150 shots into `visual-ref/old/`; verify
   `design-specs/web/manifest.json` SHAs still match (0 mismatch, same check U4/W6b used).
7. **Dark-mode contrast:** `design-system/colors.md` §contrast table: `surface` on `--color-brand-500` is 3.81:1 and
   `surface` on `--color-accent-strong` is 3.44:1 in dark mode, both below the 4.5:1 AA text threshold. These two
   tokens are used as button/badge *backgrounds* with light text on top — darken each dark-mode value just enough to
   clear 4.5:1 (keep the same hue family; do not change the light-mode values), update both `tokens.css` and
   `colors.md`, and add/update the token contrast test if one exists (`tokens.test.ts`).

## Steps
1. Do items 1–5 first (pure text/tooling, no visual risk); verify each with the tool's own `--check` where one
   exists.
2. Item 6 (screenshot regen) can run in parallel with 1–5; it only touches `visual-ref/old/` (git-ignored) and
   `manifest.json`.
3. Item 7 last; run `pnpm visual` after changing the tokens to confirm no screen depends on the exact old shade in a
   way that now looks wrong (spot-check the primary button and the sidebar badge in both themes).
4. Full gate (FE + BE as usual) even though most changes are non-code, because item 7 touches `tokens.css`.

## Acceptance
- `web-inventory.cjs --check`, `web-specs.cjs --check`, `pending-web.cjs`, `pending.cjs` all exit 0.
- `manifest.json` SHA mismatches: 0. `design-specs/README.md` and `SKILL.md` wording corrected (grep for "82-screen"
  and stray "211" confirms).
- Both contrast pairs ≥ 4.5:1 in dark mode; light mode unchanged.

## Out of scope
- Any screen content change (that is U9/U10). Re-walking the entire old web by hand if the snapshot tool can do it
  faster — use the tool.

## Report
Use `_REPORT-TEMPLATE.md`; list each of the 7 items with its real before/after check result.
