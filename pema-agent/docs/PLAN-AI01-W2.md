# PLAN-AI01-W2 — Package W2: design the Next.js-only screens, one Design System, one place for app + web

Status: planned 2026-10-05, nothing built. Branch: `feat/ui-parity`. Recipes: `pema-agent/recipes/W2/`.
Builds on package W (`PLAN-AI01-W.md`, 211 old-web screens in `Pema Web redesign canvas/Pema Web.dc.html`) and
reuses its tooling in `.claude/skills/pema-web-design/scripts/` (`web-inventory.cjs`, `web-shots.cjs`,
`web-snapshot.cjs`, `web-specs.cjs`, `web-canvas-build.cjs`, `web-canvas.cjs`, `web-coverage.cjs`).

## 1. Why

- The web canvas covers the **old** web completely (211 ids, groups WA–WI) but, by decision D3 of package W, **none of
  the screens that exist only in the new Next.js FE**: `/admin/*` (agent admin, care admin), `/care/*` (care-agent
  supervision), `/templates`, `/login`. About 33 routes, ~70–100 frames with states and dialogs. These are exactly the
  screens that look foreign next to the old web, and U1 cannot restyle them to a design that does not exist.
- No Design System artifact exists (tokens and components live in `design-specs/web/BLOCKS.md`,
  `.agents/skills/design-system/references/`, and `frontend/src/ui` after U0). Web and KMP need one shared source.
- App canvas (82 mobile screens) and web canvas (211) are separate files with separate ids and no reverse index.

## 2. Owner decisions (2026-10-05)

1. **Patient Mobile web (group WI, 42 screens) is dropped as a Next.js target.** The designs stay as reference for the
   KMP app and Zalo; INDEX marks them `served by KMP/Zalo` and links the app-canvas ids. Revisit as a Zalo-opened
   lightweight web only when the clinic has a Zalo OA.
2. **W5 (publishing to claude.ai/design) is done by the owner with `/design-sync`**, not by a subagent. W2 only
   prepares everything so that one `/design-sync` publishes both canvases and the Design System into **one
   claude.ai/design project**.
3. Keep **two canvas files** (app, web); unify through one project, one Design System, one cross-index.

## 3. Scope

| In | Out |
|---|---|
| Inventory, shots, specs and canvas frames for every Next.js-only route and its states/dialogs (new groups `WJ` agent admin, `WK` care, `WL` CSKH/auth) | Any FE or BE code change (U-package work) |
| New blocks the agent screens need (chat/trace panes, matrix grid, SLA table, KB source list), documented in `BLOCKS.md` and mirrored as names in `src/ui` (names only, implementation is U0/U1) | Patient Mobile web rebuild |
| A Design System source (tokens, color roles, type scale, spacing, radius, components with variants and states) in the form `/design-sync` needs | Publishing (owner) |
| Cross-index app ↔ web ids; WI rows marked `served by KMP/Zalo`; skill consolidation note | Deleting old canvases or skills |

## 4. Steps (one recipe each)

| Step | Scope | Needs |
|---|---|---|
| **W7** Next.js-only inventory | ids `WJ*`, `WK*`, `WL*` from FE routes + states/dialogs found in components and tests; `inventory.json` frozen | — |
| **W8** Shots | `pnpm visual`-style Playwright shots of the new ids against the mock BE at 1440×900, 1920×1020, 390×844 → `manifest.json` (PNGs not committed) | W7 |
| **W9** Specs | `web-specs.cjs` for the new ids → `design-specs/web/screens/WJ*.md…`, INDEX regenerated | W7 (W8 in parallel) |
| **W10** Canvas frames + blocks | `parts/WJ.js`, `WK.js`, `WL.js`; new blocks in `blocks.js` + `BLOCKS.md`; `web-canvas-build.cjs`; `web-canvas.cjs check --complete --viewport=all --frames` for all ids | W8, W9 |
| **W11** Design System source | `design-system/` folder ready for `/design-sync`: tokens (from `frontend/src/ui/tokens.json` if U0 exists, else from BLOCKS/skill refs), color roles, type scale, spacing, radius, shadows, components with variants/states, usage notes; both canvases reference it | W10 (can start after W7) |
| **W12** Unify | `design-specs/INDEX.md` cross-index app ↔ web; WI rows → `served by KMP/Zalo`; one project layout for `/design-sync` (what to publish, in which order); note which of `pema-web-to-canvas` / `pema-web-design` is the canonical skill | W11 |
| **W5** Publish | Owner runs `/design-sync` following `recipes/W2/07-W5-owner-publish.md`; records the links in HANDOFF | W12 |

Order: W7 → (W8 ‖ W9) → W10 → W11 → W12 → W5 (owner).

## 5. Gate per step (director runs it in the worktree before merging)

- `node .claude/skills/pema-web-design/scripts/web-inventory.cjs --check` = 0 (W7+).
- Every new id has 3 viewports in `manifest.json` (W8), one spec (W9), one frame per viewport (W10).
- `web-canvas.cjs check --complete --viewport=all --frames` = 0 for **all** ids (old 211 + new).
- `web-coverage.cjs` table counts equal across inventory / specs / canvas.
- Local viewer renders `Pema Web.dc.html` with 0 page errors.
- No file outside `design-specs/`, `Pema Web redesign canvas/`, `pema-agent/recipes/W2`, `pema-agent/docs`,
  `.claude/skills/pema-web-design/` (and the new `design-system/` folder) is touched. No attribution in commits.

## 6. Acceptance

- Inventory = old 211 + every Next.js-only route and its states; nothing with `Next.js status = exists-undesigned`.
- Design System source complete enough that a reviewer can answer "what colour/type/spacing/component does this
  frame use" for every block.
- Cross-index lets a reader go app id ↔ web id in one table; WI rows carry their KMP/Zalo mapping.
- `/design-sync` run by the owner publishes app canvas, web canvas and Design System into one project without manual
  fixes (W2 reports the exact commands).

## 7. Known facts and risks

- Account currently has **no published artifacts**; the earlier "pushed to claude.ai/design" note for the app canvas
  (2026-09-23) may refer to another account or an unpublished local sync — verify at W5.
- `_ds/novaestate-design-system-…` exists in the repo under an unrelated name; W11 inspects it and either reuses or
  retires it (do not guess).
- Agent-admin screens are ports of the zalo-agent dashboard; their structure differs from clinic screens. Design
  them with the Pema shell and blocks, keep their information architecture.
