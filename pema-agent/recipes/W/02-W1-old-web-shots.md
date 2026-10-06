# W1 — Screenshots of every old-web screen (way 1)

## Goal
Fill `pema-agent/frontend/visual-ref/old/` with a deterministic screenshot of every inventory id at the 5 viewports,
plus a tracked `manifest.json`. The old shots are then:
- the side-by-side reference for U4–U8;
- the image source for the specs (W2) and the canvas (W3).

## Read first
1. `PLAN-AI01-W.md` (§2 principle 4 "deterministic", decision D5).
2. `design-specs/web/inventory.json` and `.claude/skills/pema-web-design/scripts/lib/old-web.cjs` (from W0).
3. `pema-agent/frontend/visual-ref/old/README.md` and `../new/README.md`. The legacy names `<width>-<screen>.png` are
   what U0 and U8 compare against.
4. `prototype/review-desktop.cjs`, for its overflow metrics (`pageWidth`, `.content` width). Read it only; never run
   or edit it.

## Ingredients
- `.claude/skills/pema-web-design/scripts/web-shots.cjs`
  - `node web-shots.cjs [--only=WB,WC3]` captures every id × every viewport into `visual-ref/old/<ID>-<W>x<H>.png`.
    It also writes the legacy copy `<W>-<legacy_shot>.png` when the inventory has `legacy_shot`.
  - `manifest.json`, one entry per image:
    `{id, viewport, file, sha256, page_width, content_width, overflow: bool, page_errors: []}`. Add `generated_from`,
    `clock` and `role`.
  - `--check` re-captures to `%TEMP%` and compares with the manifest: same file set, every page error list empty.
    - It fails when an image is missing.
    - A SHA difference counts as "changed": print the changed images. The check fails only if more than 5% of the
      images changed. Anti-aliasing noise is allowed; structural change is not.
- `visual-ref/old/index.html` (generated, git-ignored): a gallery grouped by inventory group with the 5 viewports in a
  row, for human review.
- `pema-agent/frontend/.gitignore`: add `!visual-ref/old/manifest.json` after the `visual-ref/old/*` line.
- Rewrite `visual-ref/old/README.md` to point at `web-shots.cjs` instead of `review-desktop.cjs`.

## Steps
1. For each id: open a fresh page per viewport, call `freeze(page)`, follow `reach`, wait for network idle and
   `document.fonts.ready`, then capture.
   - Capture the viewport only (not full page) for pages, so it matches the frames.
   - For a dialog or modal, capture the viewport with the dialog open.
2. Record overflow (`scrollWidth > viewport width`) as data. The old web may overflow at 390 or 1024: that is a fact
   for the parity audit, not a failure of W1.
3. Run the full capture, then `--check`. Open the gallery and look at:
   - at least one image per group at 1440;
   - every 390 image of the WB group.
   Blank or half-rendered frames (fonts missing, data not loaded) are failures. Fix them by waiting on a specific
   selector.
4. Commit the script, `manifest.json`, the README and `.gitignore`. Never commit PNGs or `index.html`.

## Acceptance
- Image count = number of inventory ids × 5, plus the legacy copies. Every `page_errors` list is empty.
- `node .claude/skills/pema-web-design/scripts/web-shots.cjs --check` exits 0.
- `git status` shows no `.png` staged. `git check-ignore` confirms the images are ignored and `manifest.json` is not.
- The U0 comparison input still exists: `visual-ref/old/1920-today.png`.

## Out of scope
- Uploading images anywhere. New-FE shots (`pnpm visual` already does them). Editing `prototype/`.

## Report
Use `_REPORT-TEMPLATE.md`. Also include:
- the overflow table (id × viewport where `overflow` is true);
- the run time of a full capture;
- the images you looked at.
