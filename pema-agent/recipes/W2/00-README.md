# Package W2 recipes — Next.js-only screens into the web canvas, one Design System, one project

One file = one step. Template: Goal → Read first → Ingredients → Steps → Acceptance → Out of scope → Report.
Source of truth: `pema-agent/docs/PLAN-AI01-W2.md`; the plan wins over a recipe. Package W tooling is reused as is:
read `pema-agent/recipes/W/00-README.md` and `pema-agent/docs/PLAN-AI01-W.md` §3 first for paths and commands.

## Order

```
01-W7-nextjs-inventory ─┬─► 02-W8-shots ──┐
                        └─► 03-W9-specs ──┴─► 04-W10-canvas-frames-blocks ─► 05-W11-design-system ─► 06-W12-unify
(publishing to claude.ai/design is deferred; not part of W2)
```

## Locations (write only here)

```
design-specs/web/inventory.json · snapshot.json · notes.json · index.json · INDEX.md · BLOCKS.md · screens/WJ*.md WK*.md WL*.md
design-specs/web/manifest.json                       shots manifest (PNGs are NOT committed)
design-specs/INDEX.md                                 cross-index app ↔ web (W12)
Pema Web redesign canvas/parts/{WJ,WK,WL}.js · blocks.js · Pema Web.dc.html · Pema Web blocks.dc.html
design-system/                                        Design System source in the repo (W11)
.claude/skills/pema-web-design/                       scripts and skill text (additive changes only)
pema-agent/docs/PLAN-AI01-W2.md · pema-agent/recipes/W2/
```

Reference only (read, never modify): `pema-agent/frontend/src/**`, `pema-agent/backend/**`, `prototype/**`,
`Pema App redesign canvas/**`, `design-specs/screens/**` (app specs), `.agents/skills/design-system/references/**`,
`.agents/skills/pema-design/references/visual-system.md`.

## Tooling (from package W)

```
S=.claude/skills/pema-web-design/scripts
node $S/web-inventory.cjs --check          ids frozen and consistent
node $S/web-shots.cjs …                    Playwright shots → manifest.json
node $S/web-snapshot.cjs …                 structure snapshot (actions/fields/statuses/notices)
node $S/web-specs.cjs                      specs + INDEX from inventory + snapshot + notes
node $S/web-canvas-build.cjs               Pema Web.dc.html from parts/*.js
node $S/web-canvas.cjs check --complete --viewport=all --frames
node $S/web-coverage.cjs                   counts table inventory / specs / canvas
```
Services: FE dev server with the mock BE (`pema-agent/frontend`, see its README), design-viewer on 4180 or the Docker
viewer on 4191. Temp files (dumps, PNGs) go to the scratchpad or `%TEMP%`, never into the repo.

## Common rules

- Old web look is the reference; agent screens keep their information architecture but use Pema shell and blocks.
- Synthetic data only in shots (mock BE). Vietnamese labels exactly as the FE shows them.
- Frames: 1440×900 primary, plus 1920×1020 and 390×844 for pages (dialogs/states may use 1440 only — follow package
  W's D4 convention).
- Do not change FE/BE code. Do not touch the app canvas file. No attribution in commits.
- Report ≤ 30 lines using `_REPORT-TEMPLATE.md`, with the real check outputs (counts, zeros, failures).
