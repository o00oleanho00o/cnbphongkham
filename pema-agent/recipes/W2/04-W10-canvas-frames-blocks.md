# W10 — Canvas frames for WJ/WK/WL and the blocks they need

## Goal
Every new id has frames, built from blocks that map to `src/ui`, in the Pema look — **in a separate canvas file**
`Pema Web (Next.js).dc.html`. `Pema Web.dc.html` stays old-web only (WA–WI). Owner decision 2026-10-05 ("A + dropdown").

> In-flight worktrees (w10-wj1, w10-wj2, w10-wk, w2/w10): keep writing `parts/WJ.js`, `WK.js`, `WL.js` exactly as
> before; nothing in the parts changes. The split happens in the build and merge step below, done by whoever merges.

## Read first
1. `recipes/W/04-W3a-canvas-foundation.md`, `05-W3b-canvas-screens.md`, `05b-W3c-template-fixes.md`,
   `10-W6c-canvas-new-ids.md`; `design-specs/web/BLOCKS.md`; `Pema Web redesign canvas/parts/{base,blocks,WA..WI2,tail}.js`.
2. `.agents/skills/pema-design/references/visual-system.md`, `.agents/skills/design-system/references/*`.
3. The specs and shots of W8/W9.

## Ingredients
- `parts/WJ.js`, `parts/WK.js`, `parts/WL.js` (one frame per id × viewport as D4 requires).
- `web-canvas-build.cjs` with a group→output map (additive flag or config): WA–WI → `Pema Web.dc.html`,
  WJ/WK/WL → `Pema Web (Next.js).dc.html`; both from the same `base.js`, `blocks.js`, `tail.js`.
- `web-canvas.cjs check` able to target a file (additive `--file`), so each output is checked for its own ids.
- `design-viewer/src`: a dropdown "Web cũ" (default) / "Màn mới" / "Cả hai" that loads one or both files; additive, no
  other viewer change.
- New blocks (only if no existing block fits): `AgentChatPane`, `TracePane`, `MatrixGrid` (depth × autonomy),
  `SlaTable`, `KbSourceList`, `ToolAllowlist`, `OnCallCard`, `HandoffCard`. Each gets a `BLOCKS.md` row with its
  `src/ui` name, props, states, and the ids that use it.

## Steps
1. Map each id to blocks; where the agent-admin screen's structure has no clinic equivalent, keep its information
   architecture and dress it with Pema shell/tokens.
2. Write parts; build **two files** with `web-canvas-build.cjs`; check each: old file complete for WA–WI and containing
   no WJ/WK/WL frame, new file complete for WJ/WK/WL (`--viewport=all --frames`) until 0.
3. Viewer dropdown; open both files; 0 page errors each; spot-check 10 new frames against the W8 shots.
4. Update `Pema Web blocks.dc.html` if the blocks sheet is generated from `blocks.js`.

## Acceptance
- Check = 0 per file; `Pema Web.dc.html` has no WJ/WK/WL frame (assert); coverage table equal; `BLOCKS.md` complete;
  viewer dropdown works and defaults to "Web cũ"; 0 page errors for both files.

## Out of scope
- Implementing blocks in `src/ui` (U0/U1 do that from `BLOCKS.md`).

## Report
Use `_REPORT-TEMPLATE.md`; list new blocks and which ids use them.
