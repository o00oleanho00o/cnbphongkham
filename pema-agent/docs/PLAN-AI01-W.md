# PLAN-AI01-W — Package W: design of the old Pema web (screenshots, screen specs, web canvas)

Status: **planned 2026-10-04, waiting for owner approval; nothing built.** Recipes: `pema-agent/recipes/W/`.
Proposed branch: `feat/web-design`, created from `feat/ui-parity` at `821f813`, merged back into `feat/ui-parity` when
the package is accepted.
**This clone has no U4** (studio / resources / services; `ui/u4-fix` `24dfd1c` exists only on the old machine
`E:\Desktop\cnbphongkham`, not on origin). W does not need it (see §8), but the WE group's Next.js target is "planned (U4)".

## 0. Why

The app has a full design pipeline: canvas `Pema App redesign canvas/Pema App.dc.html` (82 mobile screens A1–K3),
generated specs `design-specs/screens/<ID>.md`, MCP server `pema-design`, skills `pema-web-to-canvas` and
`pema-canvas-to-kmp-compose`. The **web has none of it**. The old Clinic Web exists only as code in `prototype/`
(read-only). Package U ports it to Next.js by reading that code directly. `pema-agent/frontend/visual-ref/old/` is empty
on this clone, because the images are git-ignored and the capture script requires Playwright from another machine's
path.

Owner request (2026-10-04): build all three missing layers, each by subagents following recipes:

1. **Screenshots** of every old web screen at the 5 viewports, so package U (U4–U8) can compare old and new
   side by side.
2. **Screen specs** for every old web screen, generated like the app specs and served by the same MCP server,
   so a builder reads one spec instead of re-reading `prototype/`.
3. **A web design canvas** (`Pema Web.dc.html`, web-size frames) on claude.ai/design, built from blocks that map 1:1
   to the Next.js kit `pema-agent/frontend/src/ui`, plus a skill that keeps the canvas, the specs and the shots in
   step.

**Owner rule (2026-10-04, final): the web canvas, the specs and the shots must contain EVERY piece of UI the old
web has** — every page, tab, modal, dialog, visible state, field, action, status, filter and text. Nothing is
filtered out or dropped. What comes from the app design is the **design language**, not the feature list:

| Question | Source that wins |
|---|---|
| Which screens, fields, actions, statuses, texts exist | The old web, completely |
| Colours, type, radius, spacing, component shapes | `tokens.json` (U0) and the app canvas blocks |
| How a block is drawn (card, chip, metric tile, notice, button…) | The app canvas block of the same purpose, rendered at web size |
| Sample data (names, numbers) | The app canvas `people`, `GROUPS`, `money()`; the old web's demo values are not copied |
| Business-rule sentences | Verbatim from the old web; where the app says it differently, keep the old web's text and note the app's in `notes.json` |

A screen that has no app counterpart is still built (it gets `app_canvas: []`). A difference between old web and
app is recorded in `design-specs/web/notes.json` (`differences`) for the owner; it never removes UI.

## 1. Scope

In scope, all from the old web (`prototype/`, read-only):

| Area | Source | Notes |
|---|---|---|
| Clinic Web pages (`data-nav`): dashboard, today, schedule, patients, crm, followups, studio, resources, services, cashier, finance, ask, guide | `prototype/clinic-web/index.html`, `prototype/shared/*.js` | one screen id per page |
| Patient 360 tabs (`data-tab`): overview, consult, plan, session, photos, finance, crm, history | `shared/patient.js`, `clinic.js` | one id per tab |
| Patient 360 modals (`data-modal`): note, message, edit, care, plan-edit, patient | same | one id per modal |
| Dialogs opened by buttons (list `CLINIC_DIALOGS` in `.claude/skills/pema-web-to-canvas/scripts/dump-web.cjs`) | `operations-ui.js`, `crm-ui.js`, `order-ui.js` | Đặt lịch, Check-in, Xử lý, Khóa phòng, Chỉnh dịch vụ, Thu tiền, Lên đơn nhanh, Hồ sơ mới |
| Finance web (4 tabs incl. owner / accountant / doctor projections) | `prototype/finance/*` + `finance_server.py` (port 4174) | needs the finance server for numbers |
| Order review / A5 print | `prototype/order-review/index.html` | |
| Shell: sidebar, header, role picker, empty states reachable from the UI | `workspace-layout.css`, `ui.js`, `staff-context.js` | one id per visible state |

**Scope extension (owner, 2026-10-04, repeated): nothing may be missing.** The Patient Mobile web (`prototype/patient-mobile`) is IN scope as
group WI, and every state W0 parked (native dialogs, empty and error lines, per-role variants) gets an id. Work: `recipes/W/08` to `10` (W6a
inventory completion, W6b shots and specs for the new ids, W6c canvas frames). The old line "Patient Mobile web is out of scope" no longer applies.

Out of scope:
- **Screens that exist only in the new Next.js FE** (inbox, review, templates, care/*, admin/*): see decision D3.
- App code (`pema-kmp/`), Next.js page code, the existing app canvas and its specs (`design-specs/screens/*`). These
  must stay byte-identical, except for the additive MCP change in W2.
- Deleting or editing anything in `prototype/`.

Expected size: 45–70 screen ids. W0 fixes the exact list. Nothing is filtered out.

## 2. Principles

0. **Complete coverage (owner rule).** Every old-web screen, tab, modal, dialog, state, field, action, status,
   filter and text appears in the inventory, the shots, the specs and the canvas. W0's `--check` and W4's audit
   count them. `app_canvas` is a cross-reference for reuse of blocks and wording, never a filter. Differences
   between old web and app go to `notes.json` (`differences`); see decision D8.
1. **Old web is the reference, never edited.** Serve it read-only (`python -m http.server 4173 --bind 127.0.0.1
   --directory prototype`, or `docker compose up -d pema-prototype`). Scripts live in the new skill folder.
2. **One inventory, stable ids.** `design-specs/web/inventory.json` (W0) lists every screen once:
   - id `W<group><n>`, for example `WB3`;
   - how to reach the screen (nav, tab, modal or button);
   - its source files;
   - its Next.js target route and U step;
   - its app-canvas cross-reference.
   Every later step reads this file. No step invents ids.
3. **Generated, not hand-written.** Shots, specs, `INDEX.md` and `BLOCKS.md` come from scripts with a `--check` mode.
   Human knowledge (business rules, accepted differences, gotchas) goes only into `design-specs/web/notes.json`, the
   same contract as the app specs.
4. **Deterministic.**
   - Fixed clock: the old web's demo day, chosen in W0.
   - Fixed role and fixed viewport per capture.
   - Fonts loaded before every capture.
   - Re-running a script on an unchanged tree changes nothing.
5. **Blocks = app design language = kit.** Every web canvas block is drawn like the app canvas block of the same
   purpose (`h`, `s`, `m`, `chips`, `fc`, `t`, `notice`, `dd`, `input`, `week`, `photos`, `a5`… in
   `design-specs/BLOCKS.md`), at web size, and renders one Next.js kit component (`src/ui/*`) with its KMP
   `core:ui` analogue named. Blocks the old web needs and the app has none for (data table, sidebar, week board,
   A5 print) are added and marked `web-only` in `blocks-web.md`. Tokens come from
   `pema-agent/frontend/src/ui/tokens.json` (U0); no hex values inside blocks.
6. **Synthetic data only.** The old web's demo data is synthetic. Business-rule sentences stay verbatim in
   Vietnamese:
   - "AI chỉ là bản nháp" (AI output is only a draft);
   - completed treatment is never inferred from payment;
   - messages are not an emergency channel;
   - illustrative photos do not score efficacy.
7. **Additive only on shared tooling.**
   - `pema-design-mcp.cjs` gains web tools, and its existing tools behave exactly as before.
   - `node .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs --check` must pass in every step.
8. No AI attribution in git (HARD RULE in HANDOFF/CLAUDE.md). Commit only inside step worktrees. Merge and push only
   as the director, and push only when the user says so.

## 3. Where things go

```
.claude/skills/pema-web-design/                  new skill (W0 skeleton, W4 final SKILL.md)
  scripts/lib/pw.cjs                             Playwright loader (PLAYWRIGHT_MODULE → frontend node_modules → npx cache)
  scripts/web-inventory.cjs                      W0: walk the old web → inventory.json (+ --check)
  scripts/web-shots.cjs                          W1: inventory → PNGs + manifest.json (+ --check)
  scripts/web-snapshot.cjs                       W2: inventory → structured DOM snapshot.json
  scripts/web-specs-lib.cjs, web-specs.cjs       W2: snapshot + notes + canvas (W3) → design-specs/web/
  scripts/web-canvas.cjs                         W3: list / check the web canvas through design-viewer
  references/coverage-web.md                     old web ↔ web canvas ↔ app canvas ↔ Next.js route
  references/blocks-web.md                       canvas block ↔ src/ui component ↔ KMP core:ui
design-specs/web/                                inventory.json, snapshot.json, notes.json (hand), INDEX.md, BLOCKS.md,
                                                 index.json, screens/<ID>.md (generated)
pema-agent/frontend/visual-ref/old/              <ID>-<W>x<H>.png (git-ignored), manifest.json (tracked), README.md
Pema Web redesign canvas/                        Pema Web.dc.html (GENERATED), support.js (same bytes as the app canvas copy),
                                                 parts/<group>.js (hand-written data, one file per group), template.html
.claude/skills/pema-canvas-to-kmp-compose/mcp/pema-design-mcp.cjs   + list_web_screens, get_web_screen,
                                                 get_web_screen_image, record_web_note (W2)
```

## 4. Steps (one recipe each, `recipes/W/`)

| Step | Way | Scope | Needs | Owner of files |
|---|---|---|---|---|
| **W0** Inventory + foundation | all | skill skeleton, `pw.cjs`, `web-inventory.cjs`, `inventory.json` with ids, clock and role decisions | — | skill `scripts/`, `design-specs/web/inventory.json` |
| **W1** Old web screenshots | 1 | `web-shots.cjs`, all ids × 5 viewports, `manifest.json`, gallery, legacy names for U0/U8 | W0 | `visual-ref/old/`, `web-shots.cjs` |
| **W2** Web screen specs + MCP | 2 | `web-snapshot.cjs`, `web-specs*.cjs`, `notes.json` seed, generated specs, MCP web tools | W0 (W1 for images, by file name only) | `design-specs/web/` except inventory, MCP file |
| **W3a** Web canvas foundation | 3 | canvas file, frame template, tokens, blocks in the app design language ↔ kit, build script, stub parts, proof screens WA1 + WB1, `web-canvas.cjs`, specs read canvas | W2 | canvas folder, `web-canvas.cjs`, `blocks-web.md` |
| **W3b** Web canvas screens, **8 parallel agents** W3b-WA … W3b-WH | 3 | one agent per group WA, WB, WC, WD, WE, WF, WG, WH; every inventory id of the group has a frame | W3a | each agent only its own `Pema Web redesign canvas/parts/<group>.js` and its own ids in `notes.json` |
| **W4** Skill, docs, audit | all | final `SKILL.md`, coverage table, CLAUDE.md/README pointers, change-log rule (D6), full re-run of all checks | W1, W3b | docs only |
| **W5** Push to claude.ai/design | 3 | create project, upload canvas, verify remote = local | W4 + user | **director with the user**, not a subagent |

Order: `W0 → (W1 ‖ W2) → W3a → (W3b-WA ‖ WB ‖ WC ‖ WD ‖ WE ‖ WF ‖ WG ‖ WH) → W4 → W5`. W0–W2 ran with at most 2 agents because the old web's
`http.server` drops connections above 2 browsers. W3b agents never touch the old web (they read specs and shots), so up to 8
run at once. Each agent runs its own design-viewer: `DC_CANVAS_DIR=<its worktree canvas folder> npm run dev -- --port <own port>`
from the main checkout's `design-viewer/` (deps installed once there).

Groups (W0 may rename them, but not reorder them):

| Group | Area |
|---|---|
| WA | Shell and navigation |
| WB | Operations: dashboard, today, schedule, booking/check-in |
| WC | Patients and Patient 360 tabs/modals |
| WD | CSKH: crm, followups, Xử lý |
| WE | Studio, resources, services |
| WF | Cashier, quick order, order review/A5 |
| WG | Finance PB02 |
| WH | Hỏi Pema and Hướng dẫn |

## 5. Gate per step (the director runs it in the step's worktree before merging)

- The step's own `--check` scripts: exit 0, and the counts match `inventory.json`.
- Coverage check: every field, action, status, filter and notice of the old-web snapshot (W2) appears in the spec
  and in the canvas frame. Missing items are listed by `web-specs.cjs --check` and `web-canvas.cjs check`.
- `node .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs --check`: app specs unchanged.
- `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs`: no `✗ NOT LOGGED` file. W never edits the web, so
  nothing new may appear.
- `git diff --stat feat/web-design`: only files the recipe owns. `prototype/`, `pema-kmp/`, `Pema App.dc.html` and
  `design-specs/screens/` are untouched.
- If `pema-agent/frontend` changed: `pnpm lint`, `pnpm vitest run` (count ≥ 820, the U7 baseline) and `pnpm inventory`.
- `git log --format=%B feat/web-design..HEAD | grep -i -E "co-authored|generated with|claude|anthropic"` prints
  nothing.
- The report follows `_REPORT-TEMPLATE.md`, with real command output.

## 6. Acceptance for the package

- Every `inventory.json` id has:
  - 5 screenshots in `visual-ref/old/`;
  - a spec in `design-specs/web/screens/`;
  - a frame in `Pema Web.dc.html`;
  - a row in `coverage-web.md`.
- Content matches the old web: for each id, every field, action, status and text of the snapshot is in the spec and
  the frame (coverage check 0 missing). Look and feel match the app design (tokens, blocks).
- `web-shots.cjs --check`, `web-specs.cjs --check`, `web-canvas.cjs check` and the app `design-specs.cjs --check`
  all pass.
- The MCP server answers `get_web_screen("WB1")` with the spec. The existing `get_screen("A1")` answer is unchanged.
- Canvas review: every group PNG has been opened and looked at, with no overflow and no unresolved `{{ }}`.
- The canvas is pushed to claude.ai/design, and remote = local (W5, with the user).
- HANDOFF has a "Package W" result section; `SECTION_PROGRESS.md` has a checkpoint.

## 7. Decisions for the owner (defaults apply if approved as written)

| # | Question | Default in this plan |
|---|---|---|
| D1 | Package W writes outside `pema-agent/`: `design-specs/web/`, `Pema Web redesign canvas/`, `.claude/skills/pema-web-design/`, an additive change to the MCP server, a pointer section in `CLAUDE.md`. Allowed? | Yes, these paths only |
| D2 | Branch | `feat/web-design` from `feat/ui-parity` `821f813`; merge back into `feat/ui-parity` |
| D3 | Include screens that exist only in the new Next.js FE (inbox, review, templates, care/*, admin/*) as group WI? | No for now; can be a later step that reads `pnpm visual` shots |
| D4 | Canvas frame size | 1440×900 for every screen; extra 1920×1020 and 390×844 frames for pages only (not dialogs or modals) |
| D5 | Commit screenshots? | No (git-ignored as today); commit `manifest.json` with SHA-256 per image |
| D6 | After W, is the web canvas the design-first source for new Next.js screens, with a change log like `web-changes.md` and a CLAUDE.md rule? | Yes; W4 writes the rule |
| D7 | claude.ai/design project for the web canvas | New project "Pema Web redesign canvas", created by the user in W5 |
| D8 | When the old web and the app design disagree on a label, a step or a rule sentence | Keep the old web's UI as it is; write the app's version under `differences` in `notes.json`; the owner decides later which one the Next.js FE uses |

## 8. Known facts and risks

- This clone has no U4 (`studio`, `resources`, `services` exist only on the old machine). W is not blocked, because it
  reads the old web. In specs, the Next.js target for those screens shows "planned (U4)".
- `prototype/review-desktop.cjs` requires Playwright from `C:/Users/email/...`, so it cannot be used as is. W1
  replaces it with `web-shots.cjs` and keeps the legacy file names (`<width>-<screen>.png`) that U0 and U8 expect.
- Finance numbers need `python prototype/finance_server.py --port 4174 --db <temp>/finance.sqlite3`. Use a temp DB
  path: the default writes `.local/` in the repo.
- Canvas rendering needs `design-viewer` (`cd design-viewer && npm install && npm run dev`, port 4180).
- The live Docker stack (ports 3000/8000) is not needed and does not conflict (W uses 4173, 4174, 4180).
- Worktree subagents have no `node_modules`. Set `PLAYWRIGHT_MODULE` to the main checkout's
  `pema-agent/frontend/node_modules/playwright`, where Chromium is already installed.
