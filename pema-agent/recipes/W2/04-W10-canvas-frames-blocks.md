# W10 — Canvas frames for WJ/WK/WL and the blocks they need

## Goal
Every new id has frames in `Pema Web.dc.html`, built from blocks that map to `src/ui`, in the Pema look.

## Read first
1. `recipes/W/04-W3a-canvas-foundation.md`, `05-W3b-canvas-screens.md`, `05b-W3c-template-fixes.md`,
   `10-W6c-canvas-new-ids.md`; `design-specs/web/BLOCKS.md`; `Pema Web redesign canvas/parts/{base,blocks,WA..WI2,tail}.js`.
2. `.agents/skills/pema-design/references/visual-system.md`, `.agents/skills/design-system/references/*`.
3. The specs and shots of W8/W9.

## Ingredients
- `parts/WJ.js`, `parts/WK.js`, `parts/WL.js` (one frame per id × viewport as D4 requires).
- New blocks (only if no existing block fits): `AgentChatPane`, `TracePane`, `MatrixGrid` (depth × autonomy),
  `SlaTable`, `KbSourceList`, `ToolAllowlist`, `OnCallCard`, `HandoffCard`. Each gets a `BLOCKS.md` row with its
  `src/ui` name, props, states, and the ids that use it.

## Steps
1. Map each id to blocks; where the agent-admin screen's structure has no clinic equivalent, keep its information
   architecture and dress it with Pema shell/tokens.
2. Write parts; build with `web-canvas-build.cjs`; check with `web-canvas.cjs check --complete --viewport=all --frames`
   until 0 for all ids (old + new).
3. Open the viewer; 0 page errors; spot-check 10 frames against the W8 shots.
4. Update `Pema Web blocks.dc.html` if the blocks sheet is generated from `blocks.js`.

## Acceptance
- Check = 0 for all ids; coverage table equal; `BLOCKS.md` complete; viewer clean.

## Out of scope
- Implementing blocks in `src/ui` (U0/U1 do that from `BLOCKS.md`).

## Report
Use `_REPORT-TEMPLATE.md`; list new blocks and which ids use them.
